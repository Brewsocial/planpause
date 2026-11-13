"""Planpause API.

Mandanten werden über ``Authorization: Bearer ...`` erkannt: mit Supabase
(SUPABASE_URL gesetzt) über das Zugriffstoken des angemeldeten Benutzers, sonst
über den API-Schlüssel des Betriebs (Entwicklung, Tests).
Jeder Betrieb sieht nur seine eigenen Projekte.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from planpause_engine.export import to_dxf, to_report
from planpause_engine.ifc import to_ifc, to_meshes
from planpause_engine.sheet import to_pdf
from planpause_engine.model import Measurement, PlanModel
from planpause_engine.pipeline import analyze, issues_from
from planpause_engine.purpose import PURPOSES
from planpause_engine.preprocess import Prepared, prepare

from . import billing
from .storage import NotFound, Store, UserExists

log = logging.getLogger("planpause")
SUPABASE = bool(os.environ.get("SUPABASE_URL"))
if SUPABASE:
    from .supabase_store import SupabaseStore
    store = SupabaseStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
else:
    store = Store()
DAILY_ANALYSES = int(os.environ.get("PLANPAUSE_DAILY_ANALYSES", "20"))
# Selbst-Registrierung: kostenlose Grundrisse pro neuem Betrieb und Obergrenze neuer Konten pro Tag (Schutz vor Missbrauch)
TRIAL_ANALYSES = int(os.environ.get("PLANPAUSE_TRIAL_ANALYSES", "0"))  # seit 2026-11-13 keine Gratis-Grundrisse mehr
SIGNUPS_PER_DAY = int(os.environ.get("PLANPAUSE_SIGNUPS_PER_DAY", "25"))
CONTACT = os.environ.get("PLANPAUSE_CONTACT_EMAIL", "information.kico@gmail.com")
DEMO = Path(__file__).resolve().parents[1] / "demo"
FIXTURES = Path(__file__).resolve().parents[2] / "engine" / "tests" / "fixtures"
DEMOS = {"bungalow": ("plan_bungalow.json", "bungalow.jpg"), "darmstaedter14": ("plan_darmstaedter14.json", "darmstaedter14.jpg")}

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    if not SUPABASE:  # Entwicklungs-Mandant; im Betrieb über /admin/orgs angelegt
        store.ensure_org("demo-betrieb", "Demo-Betrieb", os.environ.get("PLANPAUSE_DEMO_KEY", "demo-schluessel"))
    n = store.reset_stuck()
    if n:
        log.warning("%d unterbrochene Analysen auf Fehler gesetzt", n)
    yield


INTERNAL_KEYS = {"cost_usd", "last_cost_usd"}  # KI-Kosten: bleiben im Datensatz (projects.meta), gehen aber nie an den Browser


def _public(x):
    if isinstance(x, dict):
        return {k: _public(v) for k, v in x.items() if k not in INTERNAL_KEYS}
    if isinstance(x, list):
        return [_public(v) for v in x]
    return x


class PublicJSON(JSONResponse):
    """Standard-Antwort aller Endpunkte: entfernt interne Felder wie die KI-Kosten."""

    def render(self, content) -> bytes:
        return super().render(_public(content))


app = FastAPI(title="Planpause API", version="0.1.0", lifespan=lifespan, default_response_class=PublicJSON)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("PLANPAUSE_CORS", "http://localhost:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])


def org(authorization: str = Header(default="")) -> str:
    key = authorization.removeprefix("Bearer ").strip()
    if not key:
        raise HTTPException(401, "Nicht angemeldet")
    user = store.user_for_token(key)
    if user:
        o = store.org_for_user(user["id"])
        if not o:
            raise HTTPException(403, "Dein Konto ist noch keinem Betrieb zugeordnet.")
        return o
    o = store.org_for_key(key)
    if not o:
        raise HTTPException(401, "Nicht angemeldet oder Sitzung abgelaufen")
    return o


def _nf(fn):
    try:
        return fn()
    except NotFound:
        raise HTTPException(404, "Nicht gefunden")


# ------------------------------------------------------------------ Mandanten

class OrgIn(BaseModel):
    id: str
    name: str


def admin(x_admin_token: str = Header(default="")) -> None:
    tok = os.environ.get("PLANPAUSE_ADMIN_TOKEN")
    if not tok or tok == "bitte-aendern" and SUPABASE or not secrets.compare_digest(tok, x_admin_token):
        raise HTTPException(403, "Nicht berechtigt")


@app.post("/admin/orgs", dependencies=[Depends(admin)])
def create_org(body: OrgIn):
    key = store.ensure_org(body.id, body.name)
    return {"org": body.id, "api_key": key} if key else {"org": body.id}


class InviteIn(BaseModel):
    email: str
    redirect_to: str | None = None


@app.post("/admin/orgs/{org_id}/invite", dependencies=[Depends(admin)])
def invite(org_id: str, body: InviteIn):
    if not SUPABASE:
        raise HTTPException(501, "Einladungen gibt es nur mit Supabase")
    # Rücksprung immer explizit: Die Site URL des Supabase-Projekts gehört evtl. einer anderen App
    site = os.environ.get("PLANPAUSE_SITE_URL", "http://localhost:3000").rstrip("/")
    return _nf(lambda: store.invite(org_id, body.email.strip(), body.redirect_to or f"{site}/login?setpw=1"))


class TrialIn(BaseModel):
    trial_left: int | None  # None: ohne Begrenzung (zahlender Betrieb)


@app.patch("/admin/orgs/{org_id}", dependencies=[Depends(admin)])
def set_trial(org_id: str, body: TrialIn):
    """Probe-Kontingent ändern, z. B. nach Zahlung freischalten: {"trial_left": null}."""
    _nf(lambda: store.set_trial_left(org_id, body.trial_left))
    return {"org": org_id, "trial_left": body.trial_left}


class SignupIn(BaseModel):
    email: str
    password: str
    company: str
    business: bool = True  # False: Verbraucher (für Widerrufsrecht und Mängelrechte, siehe AGB)
    terms: bool = False


TERMS_VERSION = "2026-11"  # Stand der AGB (web/lib/legal.ts: updated); beim Ändern der AGB mit anheben
_signups: dict[str, list[float]] = {}  # Anmeldungen je IP-Adresse der letzten Stunde (nur im Speicher)


@app.post("/signup")
def signup(body: SignupIn, x_planpause_client_ip: str = Header(default="")):
    if not SUPABASE:
        raise HTTPException(501, "Registrierung gibt es nur mit Supabase")
    email = body.email.strip().lower()
    company = " ".join(body.company.split())
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email):
        raise HTTPException(400, "Bitte eine gültige E-Mail-Adresse angeben.")
    if len(body.password) < 8:
        raise HTTPException(400, "Das Passwort braucht mindestens 8 Zeichen.")
    if not 2 <= len(company) <= 80:
        raise HTTPException(400, "Bitte deinen Namen oder den deines Betriebs angeben.")
    if not body.terms:
        raise HTTPException(400, "Bitte akzeptiere die AGB.")
    now, ip = time.time(), x_planpause_client_ip or "?"
    recent = [t for t in _signups.get(ip, []) if t > now - 3600]
    if len(recent) >= 3:
        raise HTTPException(429, "Zu viele Registrierungen von diesem Anschluss. Bitte später erneut versuchen.")
    if store.orgs_created_since(now - 24 * 3600) >= SIGNUPS_PER_DAY:
        raise HTTPException(429, f"Heute sind schon sehr viele neue Konten entstanden. Bitte morgen erneut versuchen oder schreib uns an {CONTACT}.")
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))).strip("-")
    org_id = f"{slug[:40].strip('-') or 'betrieb'}-{secrets.token_hex(3)}"
    if not org_id[0].isalnum():
        org_id = "b" + org_id
    try:
        store.signup(org_id, company, email, body.password, TRIAL_ANALYSES, private=not body.business,
                     terms={"accepted_at": int(now), "version": TERMS_VERSION})
    except UserExists:
        raise HTTPException(409, "Für diese E-Mail gibt es schon ein Konto. Bitte melde dich an.")
    except Exception:  # z. B. Datenbankschema noch nicht aktualisiert (supabase/schema.sql)
        log.exception("Registrierung fehlgeschlagen")
        raise HTTPException(503, f"Die Registrierung klappt gerade nicht. Bitte später erneut versuchen oder schreib uns an {CONTACT}.")
    _signups[ip] = [*recent, now]
    log.info("Neues Konto %s (%s)", org_id, "gewerblich" if body.business else "privat")
    return {"org": org_id, "trial_left": TRIAL_ANALYSES}


# ------------------------------------------------------------------ Projekte

@app.get("/health")
def health():
    return {"ok": True, "claude": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/me")
def me(o: str = Depends(org)):
    return {"org": o, "name": store.org_name(o), "trial_left": store.trial_left(o), "private": store.is_private(o),
            "contact": CONTACT, "billing": billing.configured(), "billing_test": billing.test_mode()}


# ------------------------------------------------------------------ Bezahlung (Stripe Checkout, siehe billing.py)

PUBLIC_URL = os.environ.get("PLANPAUSE_PUBLIC_URL", "https://planpause.info-brewsocial.workers.dev").rstrip("/")


class CheckoutIn(BaseModel):
    pack: Literal["einzel", "zehn"]


def _site(origin: str) -> str:
    """Rücksprungadresse nach der Zahlung: die Seite, von der der Kauf kam, aber nur bekannte Adressen."""
    allowed = {PUBLIC_URL, "http://localhost:3000", "http://127.0.0.1:3000"}
    return origin.rstrip("/") if origin.rstrip("/") in allowed else PUBLIC_URL


def _fulfill(session: dict) -> int | None:
    """Bezahlte Sitzung gutschreiben (genau einmal). Liefert die Zahl der neu gutgeschriebenen Grundrisse."""
    got = billing.paid_credits(session)
    if not got:
        return None
    o, credits = got
    if not store.record_payment(session["id"], o, credits, int(session.get("amount_total") or 0)):
        return 0  # schon gutgeschrieben
    left = store.trial_left(o)
    if left is not None:  # None: Betrieb ohne Begrenzung, nichts zu tun
        store.set_trial_left(o, left + credits)
    log.info("Zahlung %s: %s Grundriss(e) für %s", session["id"], credits, o)
    return credits


@app.post("/billing/checkout")
def checkout(body: CheckoutIn, origin: str = Header(default=""), authorization: str = Header(default=""), o: str = Depends(org)):
    if store.trial_left(o) is None:
        raise HTTPException(400, "Dein Betrieb hat bereits unbegrenzt Grundrisse.")
    user = store.user_for_token(authorization.removeprefix("Bearer ").strip()) or {}
    try:
        return billing.create_checkout(o, body.pack, user.get("email"), _site(origin))
    except billing.BillingError as e:
        log.error("Checkout fehlgeschlagen: %s", e)
        raise HTTPException(503, f"Die Bezahlung klappt gerade nicht. Bitte später erneut versuchen oder schreib uns an {CONTACT}.")


class ConfirmIn(BaseModel):
    session_id: str = Field(pattern=r"^cs_[A-Za-z0-9_]{10,200}$")


@app.post("/billing/confirm")
def confirm(body: ConfirmIn, o: str = Depends(org)):
    """Nach der Rückkehr von Stripe: Zahlung sofort gutschreiben, ohne auf den Webhook zu warten."""
    try:
        s = billing.get_session(body.session_id)
    except billing.BillingError:
        raise HTTPException(404, "Diese Zahlung kennen wir nicht.")
    if (s.get("metadata") or {}).get("org") != o:
        raise HTTPException(404, "Diese Zahlung kennen wir nicht.")
    added = _fulfill(s)
    return {"paid": s.get("payment_status") == "paid", "added": added or 0, "trial_left": store.trial_left(o)}


@app.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook nicht eingerichtet")
    payload = await request.body()
    try:
        billing.verify_webhook(payload, request.headers.get("stripe-signature", ""), secret)
    except billing.BillingError as e:
        raise HTTPException(400, str(e))
    event = json.loads(payload)
    if event.get("type") in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        _fulfill(event["data"]["object"])
    return {"ok": True}


# Begriffe: In der Oberfläche ist ein "Projekt" ein Ordner (z. B. ein Haus) mit mehreren "Grundrissen".
# In der API heißen Grundrisse aus historischen Gründen "projects", Projekte/Ordner "folders".
# Ordner liegen in derselben Ablage wie Grundrisse (meta.kind = "folder"), damit kein neues Datenbankschema nötig ist.

FLOORS = ["KG", "EG", "OG", "1. OG", "2. OG", "3. OG", "DG", "Spitzboden"]


def _is_folder(m: dict) -> bool:
    return m.get("kind") == "folder"


def _plans(o: str) -> list[dict]:
    return [m for m in store.list(o) if not _is_folder(m)]


def _folder(o: str, fid: str) -> dict:
    m = _nf(lambda: store.meta(o, fid))
    if not _is_folder(m):
        raise HTTPException(404, "Projekt nicht gefunden")
    return m


def _clean(v: str | None, n: int = 40) -> str:
    return (v or "").strip()[:n]


@app.get("/projects")
def list_projects(o: str = Depends(org)):
    return _plans(o)


MAX_UPLOAD = 25 * 1024 * 1024


def _parse_crop(crop: str) -> tuple[float, float, float, float] | None:
    if not crop.strip():
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in crop.split(","))
    except ValueError:
        raise HTTPException(422, "Ausschnitt bitte als x0,y0,x1,y1 (Anteile 0 bis 1) angeben.")
    return x0, y0, x1, y1


@app.post("/pdf/pages")
async def pdf_page_preview(file: UploadFile = File(...), o: str = Depends(org)):
    """Seitenvorschau einer PDF, damit in der App die richtige Seite gewählt werden kann."""
    from planpause_engine.pdf import is_pdf, pdf_pages
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Datei größer als 25 MB")
    if not is_pdf(data):
        raise HTTPException(422, "Das ist keine PDF-Datei.")
    try:
        return {"pages": pdf_pages(data)}
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/projects")
async def create_project(file: UploadFile = File(...), name: str = Form(""), notes: str = Form(""),
                         folder_id: str = Form(""), floor: str = Form(""), part: str = Form(""),
                         page: int = Form(1), crop: str = Form(""), o: str = Depends(org)):
    from planpause_engine.pdf import is_pdf, prepare_pdf
    if folder_id:
        _folder(o, folder_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Datei größer als 25 MB")
    pdf = is_pdf(data)
    try:
        prep = prepare_pdf(data, page, _parse_crop(crop)) if pdf else prepare(data)
    except ValueError as e:
        raise HTTPException(422, str(e) if pdf else "Bild konnte nicht gelesen werden. Bitte JPEG, PNG oder PDF hochladen.")
    pid = store.create(o, name or (file.filename or "Grundriss").rsplit(".", 1)[0])
    store.write_bytes(o, pid, "original.pdf" if pdf else "original" + Path(file.filename or "x.jpg").suffix.lower()[:5], data)
    store.write_bytes(o, pid, "prepared.jpg", prep.jpeg(quality=88))
    return store.update_meta(o, pid, status="aufbereitet", notes=notes, steps=prep.steps, image_size=list(prep.size),
                             warnings=[] if pdf else image_warnings(_original_size(data)), folder_id=folder_id or None,
                             floor=_clean(floor, 20) or "EG", part=_clean(part), source="pdf" if pdf else "foto",
                             pdf_page=page if pdf else None)


@app.post("/projects/demo/{demo}")
def create_demo(demo: Literal["bungalow", "darmstaedter14"], folder_id: str = "", o: str = Depends(org)):
    plan_file, img = DEMOS[demo]
    plan = PlanModel.model_validate(json.loads((FIXTURES / plan_file).read_text()))
    if folder_id:
        _folder(o, folder_id)
    else:  # Beispiele landen in einem eigenen Projekt
        folder_id = store.create(o, f"Beispiel: {plan.title}")
        store.update_meta(o, folder_id, kind="folder", status="ordner", demo=True)
    pid = store.create(o, plan.title)
    store.write_bytes(o, pid, "prepared.jpg", (DEMO / img).read_bytes())
    _save_plan(o, pid, plan)
    return store.update_meta(o, pid, status="analysiert", demo=True, folder_id=folder_id, floor="EG", part="")


class PlanPatch(BaseModel):
    name: str | None = None
    floor: str | None = None
    part: str | None = None
    folder_id: str | None = None  # "" = aus dem Projekt lösen


@app.patch("/projects/{pid}")
def patch_project(pid: str, body: PlanPatch, o: str = Depends(org)):
    m = _nf(lambda: store.meta(o, pid))
    if _is_folder(m):
        raise HTTPException(404, "Nicht gefunden")
    kw = {}
    if body.name is not None and body.name.strip():
        kw["name"] = _clean(body.name, 120)
    if body.floor is not None:
        kw["floor"] = _clean(body.floor, 20) or "EG"
    if body.part is not None:
        kw["part"] = _clean(body.part)
    if body.folder_id is not None:
        if body.folder_id:
            _folder(o, body.folder_id)
        kw["folder_id"] = body.folder_id or None
    return store.update_meta(o, pid, **kw)


# ------------------------------------------------------------------ Projekte (Ordner) und Geschosse

class FolderIn(BaseModel):
    name: str
    purpose: str | None = None  # Verwendungszweck, Schlüssel aus PURPOSES


def _purpose_key(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if v not in PURPOSES:
        raise HTTPException(422, "Unbekannter Verwendungszweck. Möglich: " + ", ".join(PURPOSES))
    return v


def _purpose_of(o: str, meta: dict) -> str | None:
    """Verwendungszweck des Projekts, zu dem ein Grundriss gehört (None ohne Projekt oder ohne Angabe)."""
    if not meta.get("folder_id"):
        return None
    try:
        return _folder(o, meta["folder_id"]).get("purpose") or None
    except HTTPException:
        return None


class Placement(BaseModel):
    dx: float = 0.0
    dy: float = 0.0
    rot: Literal[0, 90, 180, 270] = 0
    dz: float = Field(0.0, ge=-1000, le=1000)  # Höhenversatz des Teils in cm (versetzte Geschosse)


class FolderPatch(BaseModel):
    name: str | None = None
    purpose: str | None = None  # "" löscht den Zweck
    assembly: dict[str, dict[str, Placement]] | None = None  # Geschoss -> Grundriss-ID -> Lage


@app.get("/folders")
def list_folders(o: str = Depends(org)):
    allm = store.list(o)
    folders = [m for m in allm if _is_folder(m)]
    plans = [m for m in allm if not _is_folder(m)]
    ids = {f["id"] for f in folders}
    for f in folders:
        own = [p for p in plans if p.get("folder_id") == f["id"]]
        f["plans"] = own
        f["updated"] = max([f.get("updated", 0)] + [p.get("updated", 0) for p in own])
    folders.sort(key=lambda f: -f["updated"])
    return {"folders": folders, "unassigned": [p for p in plans if p.get("folder_id") not in ids]}


@app.post("/folders")
def create_folder(body: FolderIn, o: str = Depends(org)):
    name = _clean(body.name, 120)
    if not name:
        raise HTTPException(422, "Bitte einen Namen für das Projekt angeben.")
    fid = store.create(o, name)
    return store.update_meta(o, fid, kind="folder", status="ordner", purpose=_purpose_key(body.purpose))


@app.get("/folders/{fid}")
def get_folder(fid: str, o: str = Depends(org)):
    f = _folder(o, fid)
    return {"folder": f, "plans": [p for p in _plans(o) if p.get("folder_id") == fid], "floors": FLOORS}


@app.patch("/folders/{fid}")
def patch_folder(fid: str, body: FolderPatch, o: str = Depends(org)):
    f = _folder(o, fid)
    kw = {}
    if body.name is not None and body.name.strip():
        kw["name"] = _clean(body.name, 120)
    if body.assembly is not None:
        asm = dict(f.get("assembly") or {})
        for floor, places in body.assembly.items():
            asm[_clean(floor, 20)] = {pid: p.model_dump() for pid, p in places.items()}
        kw["assembly"] = asm
    if body.purpose is not None:
        kw["purpose"] = _purpose_key(body.purpose)
    out = store.update_meta(o, fid, **kw)
    if body.purpose is not None and kw["purpose"] != (f.get("purpose") or None):
        # Zweck steuert Prüfung und Sortierung: alle Grundrisse des Projekts neu prüfen (ohne KI, nur Rechnung)
        for p in _plans(o):
            if p.get("folder_id") == fid and p.get("status") == "analysiert":
                _save_plan(o, p["id"], _plan(o, p["id"]))
    return out


@app.delete("/folders/{fid}")
def delete_folder(fid: str, o: str = Depends(org)):
    _folder(o, fid)
    for p in _plans(o):
        if p.get("folder_id") == fid:
            store.delete(o, p["id"])
    store.delete(o, fid)
    return {"ok": True}


def _floor_geometry(o: str, fid: str, floor: str) -> dict:
    from planpause_engine.combine import combine, default_layout
    f = _folder(o, fid)
    plans = sorted((p for p in _plans(o) if p.get("folder_id") == fid and (p.get("floor") or "EG") == floor
                    and p.get("status") == "analysiert"), key=lambda p: p.get("created", 0))
    geoms = [store.read_json(o, p["id"], "result.json")["geometry"] for p in plans]
    if not geoms:
        raise HTTPException(404, f"Im Geschoss „{floor}“ gibt es noch keinen analysierten Grundriss.")
    saved = (f.get("assembly") or {}).get(floor, {})
    auto = default_layout([(g["bbox"][2] - g["bbox"][0], g["bbox"][3] - g["bbox"][1]) for g in geoms])
    parts = []
    for p, g, a in zip(plans, geoms, auto):
        place = saved.get(p["id"]) or {"dx": a["dx"] - g["bbox"][0], "dy": -g["bbox"][1], "rot": 0}
        parts.append({"id": p["id"], "label": p.get("part") or p["name"], "geometry": g, **place})
    merged = combine(parts)
    merged["floor"] = floor
    merged["saved"] = bool(saved)
    return merged


@app.get("/folders/{fid}/floors/{floor}/geometry")
def floor_geometry(fid: str, floor: str, o: str = Depends(org)):
    return _floor_geometry(o, fid, floor)


@app.get("/folders/{fid}/floors/{floor}/export/dxf")
def floor_dxf(fid: str, floor: str, unit: Literal["mm", "cm", "m"] = "mm", o: str = Depends(org)):
    f = _folder(o, fid)
    g = _floor_geometry(o, fid, floor)
    data = to_dxf(g, [], unit, f"{f['name']} – {floor}")
    return Response(data, media_type="application/dxf", headers={"Content-Disposition": f'attachment; filename="{_slug(f["name"])}_{_slug(floor)}.dxf"'})


def _scale_ok(scale: int | None):
    if scale is not None and scale not in (50, 100, 200, 250, 500):
        raise HTTPException(422, "Maßstab 1:50, 1:100, 1:200, 1:250 oder 1:500.")


@app.get("/folders/{fid}/floors/{floor}/export/pdf")
def floor_pdf(fid: str, floor: str, scale: int | None = Query(None, description="Maßstabszahl: 50, 100, 200, 250 oder 500"), o: str = Depends(org)):
    """Grundriss des Geschosses als maßstäblicher PDF-Plan (ohne Angabe der größte Maßstab, der auf A4/A3 passt)."""
    _scale_ok(scale)
    f = _folder(o, fid)
    data = to_pdf(_floor_geometry(o, fid, floor), f["name"], floor, scale, north=(f.get("building") or {}).get("north"))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{_slug(f["name"])}_{_slug(floor)}.pdf"'})


@app.get("/folders/{fid}/floors/{floor}/model")
def floor_model(fid: str, floor: str, height: float = Query(250, ge=180, le=600), o: str = Depends(org)):
    """3D-Ansicht des Geschosses: Dreiecksnetze aus demselben IFC-Modell wie beim Download."""
    f = _folder(o, fid)
    return to_meshes(to_ifc([{"name": floor, "geometry": _floor_geometry(o, fid, floor)}], f"{f['name']} – {floor}", height))


@app.get("/folders/{fid}/floors/{floor}/export/ifc")
def floor_ifc(fid: str, floor: str, height: float = Query(250, ge=180, le=600), o: str = Depends(org)):
    f = _folder(o, fid)
    data = to_ifc([{"name": floor, "geometry": _floor_geometry(o, fid, floor)}], f"{f['name']} – {floor}", height)
    return Response(data, media_type="application/x-step", headers={"Content-Disposition": f'attachment; filename="{_slug(f["name"])}_{_slug(floor)}.ifc"'})


# ------------------------------------------------------------------ Gebäude in 3D
# Die Geschosse eines Projekts übereinander: Geschosshöhe (Fußboden bis Fußboden, z. B. aus dem Schnitt) und Anzahl
# baugleicher Geschosse je Geschoss. Das Erdgeschoss liegt auf ±0, darunter liegende Geschosse nach unten.

DEFAULT_STOREY = 275.0  # cm, wenn der Nutzer nichts angibt
BUILDING_SLAB = 20.0


class StoreyIn(BaseModel):
    height: float = Field(DEFAULT_STOREY, ge=200, le=800)  # cm, Fußboden bis Fußboden
    repeat: int = Field(1, ge=1, le=40)


class BuildingIn(BaseModel):
    floors: dict[str, StoreyIn] = {}
    roof: bool = True
    north: float | None = Field(None, ge=0, lt=360)  # Grad im Uhrzeigersinn von „oben im Plan“, None = unbekannt


def _building(o: str, fid: str) -> dict:
    """Stapel der Geschosse mit Höhenlagen (cm). Nur Geschosse mit analysiertem Grundriss."""
    f = _folder(o, fid)
    saved = f.get("building") or {}
    have = {p.get("floor") or "EG" for p in _plans(o) if p.get("folder_id") == fid and p.get("status") == "analysiert"}
    rank = lambda fl: (FLOORS.index(fl) if fl in FLOORS else 99, fl)  # noqa: E731
    order = sorted(have, key=rank)
    rows = []
    for fl in order:
        s = (saved.get("floors") or {}).get(fl)
        rows.append({"floor": fl, "height": float(s["height"]) if s else DEFAULT_STOREY, "repeat": int(s["repeat"]) if s else 1,
                     "assumed": not s})
    below = [r for r in rows if rank(r["floor"]) < rank("EG")] if "EG" in have else []
    z = -sum(r["height"] * r["repeat"] for r in below)
    for r in rows:
        r["elevation"] = round(z, 1)
        z += r["height"] * r["repeat"]
    return {"floors": rows, "roof": saved.get("roof", True), "north": saved.get("north"), "top": round(z, 1)}


@app.get("/folders/{fid}/building")
def get_building(fid: str, o: str = Depends(org)):
    return _building(o, fid)


@app.put("/folders/{fid}/building")
def put_building(fid: str, body: BuildingIn, o: str = Depends(org)):
    _folder(o, fid)
    store.update_meta(o, fid, building={"floors": {_clean(k, 20): v.model_dump() for k, v in body.floors.items()},
                                          "roof": body.roof, "north": body.north})
    return _building(o, fid)


def _storeys(o: str, fid: str) -> list[dict]:
    """Geschosse für das IFC-Modell; baugleiche Geschosse einzeln, oberstes mit Dach."""
    b = _building(o, fid)
    if not b["floors"]:
        raise HTTPException(404, "In diesem Projekt gibt es noch keinen analysierten Grundriss.")
    out = []
    for r in b["floors"]:
        g = _floor_geometry(o, fid, r["floor"])
        for k in range(r["repeat"]):
            out.append({"name": r["floor"] if r["repeat"] == 1 else f"{r['floor']} {k + 1}", "floor": r["floor"], "geometry": g,
                        "elevation": r["elevation"] + k * r["height"], "height": r["height"] - BUILDING_SLAB,
                        "slab": BUILDING_SLAB, "assumed": r["assumed"]})
    out[-1]["roof"] = b["roof"]
    out[0]["ground"] = True  # unterste Decke liegt auf dem Erdreich
    return out


_MESH_CACHE: dict[str, list] = {}


@app.get("/folders/{fid}/building/model")
def building_model(fid: str, o: str = Depends(org)):
    """3D-Ansicht des Gebäudes. Baugleiche Geschosse werden nur einmal trianguliert und dann verschoben."""
    f = _folder(o, fid)
    out = []
    for st in _storeys(o, fid):
        one = {**st, "elevation": 0.0}
        key = json.dumps([o, fid, st["floor"], st["height"], st.get("roof", False), st.get("ground", False), f.get("assembly", {}).get(st["floor"]),
                          sorted((p["id"], p.get("updated", 0)) for p in _plans(o) if p.get("folder_id") == fid)], default=str)
        if key not in _MESH_CACHE:
            if len(_MESH_CACHE) > 64:
                _MESH_CACHE.clear()
            _MESH_CACHE[key] = to_meshes(to_ifc([one], f["name"]))
        dz = st["elevation"] / 100.0
        for m in _MESH_CACHE[key]:
            v = list(m["verts"])
            v[2::3] = [round(z + dz, 3) for z in v[2::3]]
            out.append({**m, "verts": v, "storey": st["name"]})
    return out


@app.get("/folders/{fid}/building/export/ifc")
def building_ifc(fid: str, schema: Literal["IFC4", "IFC2X3"] = "IFC4", o: str = Depends(org)):
    """schema=IFC2X3 für Programme, die nur das ältere Schema lesen (z. B. HottCAD von Hottgenroth)."""
    f = _folder(o, fid)
    data = to_ifc(_storeys(o, fid), f["name"], north=_building(o, fid)["north"], version=schema)
    name = f"{_slug(f['name'])}_gebaeude{'_ifc2x3' if schema == 'IFC2X3' else ''}.ifc"
    return Response(data, media_type="application/x-step", headers={"Content-Disposition": f'attachment; filename="{name}"'})


STOREY_TOL = 2.0  # cm: durchlaufende Bauteile müssen geschossübergreifend so genau übereinanderliegen


def storey_checks(storeys: list[dict]) -> list[dict]:
    """Geschosse als ein Gebäude: Außenwände (und Brandwände) aufeinanderfolgender Geschosse müssen übereinanderliegen.

    Jede Außenwand des oberen Geschosses braucht im unteren eine Wand gleicher Lage (alle vier Kanten innerhalb STOREY_TOL).
    Vor- und Rücksprünge sind möglich, sollen dann aber im Plan so gezeichnet sein; deshalb nur ein Hinweis je Geschosspaar."""
    out = []
    for low, up in zip(storeys, storeys[1:]):
        if low["floor"] == up["floor"]:
            continue  # baugleiche Geschosse
        lower = [w["rect"] for w in low["geometry"]["walls"] if w["kind"] in ("aussen", "brand")]
        upper = [w for w in up["geometry"]["walls"] if w["kind"] in ("aussen", "brand")]
        miss = []
        for w in upper:
            r = w["rect"]
            if not any(all(abs(a - b) <= STOREY_TOL for a, b in zip(r, q)) for q in lower):
                miss.append({"rect": r, "kind": w["kind"]})
        lb, ub = low["geometry"]["bbox"], up["geometry"]["bbox"]
        out.append({"lower": low["floor"], "upper": up["floor"], "total": len(upper), "unmatched": len(miss),
                    "ok": not miss, "bbox_shift": [round(u - l, 1) for u, l in zip(ub, lb)], "walls": miss[:20]})
    return out


@app.get("/folders/{fid}/building/checks")
def building_checks(fid: str, o: str = Depends(org)):
    """Geschossübergreifende Prüfung (Regel: durchlaufende Bauteile liegen innerhalb 20 mm übereinander)."""
    return {"pairs": storey_checks(_storeys(o, fid)), "tolerance_cm": STOREY_TOL}


def _save_plan(o: str, pid: str, plan: PlanModel) -> dict:
    result = analyze(plan, _purpose_of(o, store.meta(o, pid)))
    store.write_json(o, pid, "plan.json", plan.model_dump(mode="json"))
    store.write_json(o, pid, "result.json", result)
    store.update_meta(o, pid, quality=result["quality"]["level"])
    return result


MIN_SIDE = 1400  # Pixel; darunter sind kleine Maßzahlen erfahrungsgemäß kaum lesbar


def _original_size(data: bytes) -> tuple[int, int]:
    """Größe vor der Aufbereitung (die verkleinert und schneidet zu)."""
    import cv2
    import numpy as np
    h, w = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE).shape[:2]
    return w, h


def image_warnings(size: tuple[int, int]) -> list[str]:
    """Hinweise vor der (kostenpflichtigen) KI-Analyse."""
    w, h = size
    if min(w, h) < MIN_SIDE:
        return [f"Das Bild ist mit {w} × {h} Pixeln klein. Kleine Maßzahlen sind so oft nicht lesbar. "
                "Besser das Original mit der Handykamera fotografieren statt ein Bildschirmfoto zu verwenden."]
    return []


def _run_extraction(o: str, pid: str) -> None:
    from planpause_engine.extract import extract_plan
    try:
        store.update_meta(o, pid, status="analyse")
        prep = Prepared.load(store.read_bytes(o, pid, "prepared.jpg"))  # gleiches Koordinatensystem wie die Anzeige
        meta = store.meta(o, pid)
        plan, info = extract_plan(prep, meta.get("notes", ""), purpose=_purpose_of(o, meta))
        store.write_json(o, pid, "extraction_log.json", info)
        _add_cost(o, pid, info)
        _save_plan(o, pid, plan)
        store.update_meta(o, pid, status="analysiert", error=None)
    except Exception as e:  # noqa: BLE001 – Fehler soll im Projekt sichtbar werden
        log.exception("Analyse fehlgeschlagen")
        if getattr(e, "log", None):  # Tokenverbrauch auch fehlgeschlagener Läufe festhalten
            store.write_json(o, pid, "extraction_log.json", e.log)
            _add_cost(o, pid, e.log)
        store.update_meta(o, pid, status="fehler", error=_friendly_error(e))
        left = store.trial_left(o)
        if left is not None:  # fehlgeschlagene Analyse zählt nicht gegen die kostenlosen Grundrisse
            store.set_trial_left(o, left + 1)


def _add_cost(o: str, pid: str, info: dict) -> None:
    """KI-Kosten am Projekt mitschreiben: letzte Analyse und Summe (auch fehlgeschlagene Läufe kosten Geld)."""
    c = float(info.get("cost_usd") or 0)
    total = float(store.meta(o, pid).get("cost_usd") or 0)
    store.update_meta(o, pid, last_cost_usd=round(c, 4), cost_usd=round(total + c, 4))


def _friendly_error(e: Exception) -> str:
    """KI-Fehler in Hinweise übersetzen, mit denen Nutzer etwas anfangen können (Details stehen im Server-Log)."""
    import anthropic
    if isinstance(e, anthropic.BadRequestError) and "credit balance" in str(e):
        return "Das KI-Guthaben ist aufgebraucht. Bitte den Betreiber von Planpause informieren und es später erneut versuchen."
    if isinstance(e, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "Der Zugang zur KI ist ungültig. Bitte den Betreiber von Planpause informieren."
    if isinstance(e, anthropic.RateLimitError):
        return "Die KI ist gerade ausgelastet. Bitte in ein bis zwei Minuten erneut versuchen."
    if isinstance(e, anthropic.InternalServerError | anthropic.APIConnectionError):
        return "Die KI war nicht erreichbar. Bitte in ein paar Minuten erneut versuchen."
    if isinstance(e, ValueError):
        return str(e)[:500]  # eigene, bereits verständliche Meldungen (Ablehnung, abgeschnitten, kein Planmodell)
    return "Bei der Analyse ist ein unerwarteter Fehler aufgetreten. Bitte erneut versuchen."


class AnalyzeIn(BaseModel):
    consent: bool = False  # Verbraucher: Auswertung soll sofort beginnen, Widerrufsrecht erlischt (AGB § 9)


@app.post("/projects/{pid}/analyze")
def start_analysis(pid: str, bg: BackgroundTasks, body: AnalyzeIn | None = None, o: str = Depends(org)):
    meta = _nf(lambda: store.meta(o, pid))
    private = store.is_private(o)
    if private and not (body and body.consent):
        raise HTTPException(428, "Bitte bestätige vor der Auswertung, dass sie sofort beginnen soll und dein Widerrufsrecht damit erlischt.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Kein ANTHROPIC_API_KEY gesetzt. Für Tests ein Demo-Projekt anlegen.")
    if meta.get("status") == "analyse":
        raise HTTPException(409, "Die Analyse läuft bereits.")
    since = time.time() - 24 * 3600
    if sum(1 for m in store.list(o) for t in m.get("analyses", []) if t > since) >= DAILY_ANALYSES:
        raise HTTPException(429, f"Tageslimit von {DAILY_ANALYSES} Analysen erreicht. Bitte morgen weitermachen.")
    left = store.trial_left(o)
    if left is not None:
        if left <= 0:
            raise HTTPException(402, "Kein Guthaben verfügbar. Unter „Projekte“ kannst du Grundrisse kaufen." if billing.configured()
                                else f"Deine kostenlosen Grundrisse sind aufgebraucht. Für weitere Grundrisse schreib uns an {CONTACT}.")
        store.set_trial_left(o, left - 1)
    bg.add_task(_run_extraction, o, pid)
    extra = {"consents": [*meta.get("consents", []), time.time()]} if private else {}  # Nachweis der Zustimmung
    return store.update_meta(o, pid, status="analyse", analyses=[*meta.get("analyses", []), time.time()], **extra)


@app.get("/projects/{pid}")
def get_project(pid: str, o: str = Depends(org)):
    meta = _nf(lambda: store.meta(o, pid))
    return {"meta": meta,
            "plan": store.read_json(o, pid, "plan.json", {}),
            "result": store.read_json(o, pid, "result.json", {}),
            "answers": store.read_json(o, pid, "answers.json", {})}


@app.delete("/projects/{pid}")
def delete_project(pid: str, o: str = Depends(org)):
    _nf(lambda: store.delete(o, pid))
    return {"ok": True}


@app.get("/projects/{pid}/image")
def get_image(pid: str, max: int = 0, o: str = Depends(org)):
    """Aufbereitetes Bild; mit ?max=… verkleinert (Vorschaubilder, PDF-Seiten sind mehrere tausend Pixel groß)."""
    data = _nf(lambda: store.read_bytes(o, pid, "prepared.jpg"))
    if max > 0:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        k = min(1.0, max / float(img.shape[0] if img.shape[0] > img.shape[1] else img.shape[1]))
        if k < 1:
            img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


def _slug(name: str) -> str:
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", name.replace("ß", "ss")).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "_" for c in ascii_name).strip("_")[:60] or "grundriss"


def _plan(o: str, pid: str) -> PlanModel:
    return PlanModel.model_validate(_nf(lambda: store.read_json(o, pid, "plan.json")))


@app.put("/projects/{pid}/plan")
def put_plan(pid: str, plan: PlanModel, o: str = Depends(org)):
    errs = plan.validate_refs()
    if errs:
        raise HTTPException(422, errs[:10])
    result = _save_plan(o, pid, plan)
    store.update_meta(o, pid, status="analysiert")
    return result


class MeasureIn(BaseModel):
    axis: Literal["x", "y"]
    a: str
    b: str
    value: float
    note: str = ""


@app.post("/projects/{pid}/measurements")
def add_measurement(pid: str, m: MeasureIn, o: str = Depends(org)):
    plan = _plan(o, pid)
    if m.a not in plan.line_ids(m.axis) or m.b not in plan.line_ids(m.axis):
        raise HTTPException(422, "Unbekannte Linie")
    if not 0 < m.value < 10000:
        raise HTTPException(422, "Messwert in cm zwischen 0 und 10.000 angeben")
    plan.measurements = [x for x in plan.measurements if {x.a, x.b} != {m.a, m.b} or x.axis != m.axis]
    plan.measurements.append(Measurement(id="m" + secrets.token_hex(3), **m.model_dump()))
    return _save_plan(o, pid, plan)


@app.delete("/projects/{pid}/measurements/{mid}")
def delete_measurement(pid: str, mid: str, o: str = Depends(org)):
    plan = _plan(o, pid)
    plan.measurements = [x for x in plan.measurements if x.id != mid]
    return _save_plan(o, pid, plan)


@app.put("/projects/{pid}/answers")
def put_answers(pid: str, answers: dict[str, str], o: str = Depends(org)):
    _nf(lambda: store.meta(o, pid))
    store.write_json(o, pid, "answers.json", answers)
    return answers


@app.get("/projects/{pid}/model")
def plan_model(pid: str, height: float = Query(250, ge=180, le=600), o: str = Depends(org)):
    """3D-Ansicht: Dreiecksnetze aus demselben IFC-Modell wie beim Download."""
    meta = _nf(lambda: store.meta(o, pid))
    result = store.read_json(o, pid, "result.json")
    if not result.get("geometry"):
        raise HTTPException(409, "Der Grundriss ist noch nicht analysiert.")
    return to_meshes(to_ifc([{"name": meta.get("floor") or "EG", "geometry": result["geometry"]}], meta["name"], height))


@app.get("/projects/{pid}/export/{fmt}")
def export(pid: str, fmt: Literal["dxf", "ifc", "pdf", "md", "json"], unit: Literal["mm", "cm", "m"] = "mm",
           height: float = Query(250, ge=180, le=600), scale: int | None = Query(None, description="Maßstabszahl: 50, 100, 200, 250 oder 500"),
           o: str = Depends(org)):
    meta = _nf(lambda: store.meta(o, pid))
    plan, result = _plan(o, pid), store.read_json(o, pid, "result.json")
    slug = _slug(meta["name"])
    if fmt == "dxf":
        data = to_dxf(result["geometry"], issues_from(result), unit, plan.title or meta["name"])
        return Response(data, media_type="application/dxf", headers={"Content-Disposition": f'attachment; filename="{slug}.dxf"'})
    if fmt == "pdf":
        _scale_ok(scale)
        try:
            folder = _folder(o, meta["folder_id"]) if meta.get("folder_id") else {}
        except HTTPException:  # Projekt gelöscht: ohne Nordrichtung
            folder = {}
        data = to_pdf(result["geometry"], plan.title or meta["name"], meta.get("floor") or "", scale,
                      north=(folder.get("building") or {}).get("north"))
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'})
    if fmt == "ifc":  # height: lichte Raumhöhe in cm (Annahme, steht im Grundriss meist nicht)
        data = to_ifc([{"name": meta.get("floor") or "EG", "geometry": result["geometry"]}], plan.title or meta["name"], height)
        return Response(data, media_type="application/x-step", headers={"Content-Disposition": f'attachment; filename="{slug}.ifc"'})
    if fmt == "md":
        md = to_report(plan.title or meta["name"], result["geometry"], issues_from(result), store.read_json(o, pid, "answers.json", {}),
                       checklist=result.get("checklist"), annotations=result.get("annotations"), purpose=result.get("purpose") or "")
        return PlainTextResponse(md, headers={"Content-Disposition": f'attachment; filename="{slug}_pruefbericht.md"'})
    return {"plan": plan.model_dump(mode="json"), "result": result}


# ------------------------------------------------------------------ Web-App (optional)
# Mit PLANPAUSE_STATIC_DIR (Pfad zu web/out) liefert die API auch die statische Web-App aus:
# eine Adresse für alles, z. B. hinter einem Cloudflare-Tunnel. Muss die letzte Route bleiben,
# damit sie keine API-Pfade verdeckt.
STATIC = Path(os.environ["PLANPAUSE_STATIC_DIR"]).resolve() if os.environ.get("PLANPAUSE_STATIC_DIR") else None

if STATIC:
    from fastapi.responses import FileResponse

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        for cand in (STATIC / path, STATIC / f"{path}.html", STATIC / path / "index.html"):
            f = cand.resolve()
            if f.is_file() and f.is_relative_to(STATIC):
                return FileResponse(f)
        return FileResponse(STATIC / "404.html", status_code=404)
