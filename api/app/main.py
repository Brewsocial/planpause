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
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from planpause_engine.export import to_dxf, to_report
from planpause_engine.model import Measurement, PlanModel
from planpause_engine.pipeline import analyze, issues_from
from planpause_engine.preprocess import Prepared, prepare

from .storage import NotFound, Store

log = logging.getLogger("planpause")
SUPABASE = bool(os.environ.get("SUPABASE_URL"))
if SUPABASE:
    from .supabase_store import SupabaseStore
    store = SupabaseStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
else:
    store = Store()
DAILY_ANALYSES = int(os.environ.get("PLANPAUSE_DAILY_ANALYSES", "20"))
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


app = FastAPI(title="Planpause API", version="0.1.0", lifespan=lifespan)
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


# ------------------------------------------------------------------ Projekte

@app.get("/health")
def health():
    return {"ok": True, "claude": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/me")
def me(o: str = Depends(org)):
    return {"org": o, "name": store.org_name(o)}


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


class Placement(BaseModel):
    dx: float = 0.0
    dy: float = 0.0
    rot: Literal[0, 90, 180, 270] = 0


class FolderPatch(BaseModel):
    name: str | None = None
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
    return store.update_meta(o, fid, kind="folder", status="ordner")


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
    return store.update_meta(o, fid, **kw)


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


def _save_plan(o: str, pid: str, plan: PlanModel) -> dict:
    result = analyze(plan)
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
        plan, info = extract_plan(prep, store.meta(o, pid).get("notes", ""))
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


@app.post("/projects/{pid}/analyze")
def start_analysis(pid: str, bg: BackgroundTasks, o: str = Depends(org)):
    meta = _nf(lambda: store.meta(o, pid))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Kein ANTHROPIC_API_KEY gesetzt. Für Tests ein Demo-Projekt anlegen.")
    if meta.get("status") == "analyse":
        raise HTTPException(409, "Die Analyse läuft bereits.")
    since = time.time() - 24 * 3600
    if sum(1 for m in store.list(o) for t in m.get("analyses", []) if t > since) >= DAILY_ANALYSES:
        raise HTTPException(429, f"Tageslimit von {DAILY_ANALYSES} Analysen erreicht. Bitte morgen weitermachen.")
    bg.add_task(_run_extraction, o, pid)
    return store.update_meta(o, pid, status="analyse", analyses=[*meta.get("analyses", []), time.time()])


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


@app.get("/projects/{pid}/export/{fmt}")
def export(pid: str, fmt: Literal["dxf", "md", "json"], unit: Literal["mm", "cm", "m"] = "mm", o: str = Depends(org)):
    meta = _nf(lambda: store.meta(o, pid))
    plan, result = _plan(o, pid), store.read_json(o, pid, "result.json")
    slug = _slug(meta["name"])
    if fmt == "dxf":
        data = to_dxf(result["geometry"], issues_from(result), unit, plan.title or meta["name"])
        return Response(data, media_type="application/dxf", headers={"Content-Disposition": f'attachment; filename="{slug}.dxf"'})
    if fmt == "md":
        md = to_report(plan.title or meta["name"], result["geometry"], issues_from(result), store.read_json(o, pid, "answers.json", {}))
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
