"""Ablage und Anmeldung über Supabase.

Projektmetadaten liegen in der Tabelle ``planpause.projects`` (eigenes Postgres-Schema,
damit Planpause in einem bestehenden Supabase-Projekt getrennt bleibt), Bilder und
JSON-Dateien im privaten Storage-Bucket ``planpause`` unter ``<betrieb>/<projekt>/<datei>``.
Die API spricht Supabase ausschließlich mit dem Service-Schlüssel an; im Browser liegt
nur der öffentliche Schlüssel für die Anmeldung. Alle Tabellen haben RLS ohne Policies,
sind also für den Browser gesperrt (siehe ``supabase/schema.sql``).
"""
from __future__ import annotations

import json
import os
import secrets
import time

import httpx

from .storage import NotFound, _check

BUCKET = os.environ.get("PLANPAUSE_BUCKET", "planpause")
SCHEMA = os.environ.get("PLANPAUSE_DB_SCHEMA", "planpause")


class SupabaseStore:
    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        h = {"apikey": service_key}
        if not service_key.startswith("sb_"):  # alte JWT-Schlüssel zusätzlich als Bearer
            h["Authorization"] = f"Bearer {service_key}"
        self.http = httpx.Client(base_url=self.url, headers=h, timeout=30)
        self._users: dict[str, tuple[float, dict]] = {}

    # REST-Helfer -------------------------------------------------------
    def _rest(self, method: str, table: str, params: dict | None = None, body=None, prefer: str = "") -> list[dict]:
        h = {"Accept-Profile": SCHEMA} if method == "GET" else {"Content-Profile": SCHEMA}
        if prefer:
            h["Prefer"] = prefer
        r = self.http.request(method, f"/rest/v1/{table}", params=params, json=body, headers=h)
        r.raise_for_status()
        return r.json() if r.content else []

    def _obj(self, org: str, pid: str, name: str) -> str:
        return f"/storage/v1/object/{BUCKET}/{_check(org)}/{_check(pid)}/{name}"

    # Anmeldung ---------------------------------------------------------
    def user_for_token(self, token: str) -> dict | None:
        """Prüft ein Supabase-Zugriffstoken beim Auth-Server (60 s zwischengespeichert)."""
        hit = self._users.get(token)
        if hit and hit[0] > time.time():
            return hit[1]
        r = self.http.get("/auth/v1/user", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            return None
        user = r.json()
        if len(self._users) > 1000:
            self._users.clear()
        self._users[token] = (time.time() + 60, user)
        return user

    def org_for_user(self, user_id: str) -> str | None:
        rows = self._rest("GET", "org_members", {"user_id": f"eq.{user_id}", "select": "org_id"})
        return rows[0]["org_id"] if rows else None

    def org_name(self, org: str) -> str:
        rows = self._rest("GET", "orgs", {"id": f"eq.{org}", "select": "name"})
        return rows[0]["name"] if rows else org

    def org_for_key(self, key: str) -> str | None:
        return None  # im Supabase-Betrieb nur Anmeldung über Benutzerkonten

    # Mandanten ---------------------------------------------------------
    def ensure_org(self, org: str, name: str, api_key: str | None = None) -> None:
        self._rest("POST", "orgs", body={"id": _check(org), "name": name},
                   prefer="resolution=ignore-duplicates,return=minimal")

    def invite(self, org: str, email: str, redirect_to: str | None) -> dict:
        """Lädt einen Benutzer per E-Mail ein (oder findet ihn) und ordnet ihn dem Betrieb zu."""
        if not self._rest("GET", "orgs", {"id": f"eq.{_check(org)}", "select": "id"}):
            raise NotFound(org)
        r = self.http.post("/auth/v1/invite", json={"email": email},
                           params={"redirect_to": redirect_to} if redirect_to else None)
        if r.status_code == 200:
            user, invited = r.json(), True
        else:
            user, invited = self._find_user(email), False
            if not user:
                r.raise_for_status()
        self._rest("POST", "org_members", body={"user_id": user["id"], "org_id": org},
                   prefer="resolution=merge-duplicates,return=minimal")
        return {"user_id": user["id"], "email": email, "org": org, "invited": invited}

    def _find_user(self, email: str) -> dict | None:
        page = 1
        while True:
            r = self.http.get("/auth/v1/admin/users", params={"page": page, "per_page": 200})
            r.raise_for_status()
            users = r.json().get("users", [])
            for u in users:
                if (u.get("email") or "").lower() == email.lower():
                    return u
            if len(users) < 200:
                return None
            page += 1

    # Projekte ----------------------------------------------------------
    def create(self, org: str, name: str) -> str:
        pid = "p" + secrets.token_hex(6)
        now = time.time()
        meta = {"id": pid, "name": name, "status": "neu", "created": now, "updated": now}
        self._rest("POST", "projects", body={"id": pid, "org_id": _check(org), "meta": meta}, prefer="return=minimal")
        return pid

    def list(self, org: str) -> list[dict]:
        rows = self._rest("GET", "projects", {"org_id": f"eq.{_check(org)}", "select": "meta"})
        return sorted((r["meta"] for r in rows), key=lambda m: -m.get("updated", 0))

    def meta(self, org: str, pid: str) -> dict:
        rows = self._rest("GET", "projects", {"id": f"eq.{_check(pid)}", "org_id": f"eq.{_check(org)}", "select": "meta"})
        if not rows:
            raise NotFound(pid)
        return rows[0]["meta"]

    def update_meta(self, org: str, pid: str, **kw) -> dict:
        m = self.meta(org, pid)
        m.update(kw, updated=time.time())
        self._rest("PATCH", "projects", {"id": f"eq.{pid}", "org_id": f"eq.{org}"}, {"meta": m}, prefer="return=minimal")
        return m

    def delete(self, org: str, pid: str) -> None:
        self.meta(org, pid)
        r = self.http.post(f"/storage/v1/object/list/{BUCKET}", json={"prefix": f"{org}/{pid}/", "limit": 1000})
        r.raise_for_status()
        names = [f"{org}/{pid}/{o['name']}" for o in r.json()]
        if names:
            self.http.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": names}).raise_for_status()
        self._rest("DELETE", "projects", {"id": f"eq.{pid}", "org_id": f"eq.{org}"})

    def read_bytes(self, org: str, pid: str, name: str) -> bytes:
        self.meta(org, pid)
        r = self.http.get(self._obj(org, pid, name))
        if r.status_code in (400, 404):
            raise NotFound(name)
        r.raise_for_status()
        return r.content

    def write_bytes(self, org: str, pid: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        if name.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif name.endswith(".png"):
            content_type = "image/png"
        r = self.http.post(self._obj(org, pid, name), content=data,
                           headers={"Content-Type": content_type, "x-upsert": "true"})
        r.raise_for_status()

    def read_json(self, org: str, pid: str, name: str, default=None):
        try:
            return json.loads(self.read_bytes(org, pid, name))
        except NotFound:
            if default is not None:
                return default
            raise

    def write_json(self, org: str, pid: str, name: str, data) -> None:
        self.write_bytes(org, pid, name, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    # Betrieb -----------------------------------------------------------
    def reset_stuck(self) -> int:
        rows = self._rest("GET", "projects", {"meta->>status": "eq.analyse", "select": "id,org_id"})
        for r in rows:
            self.update_meta(r["org_id"], r["id"], status="fehler",
                             error="Die Analyse wurde durch einen Neustart unterbrochen. Bitte erneut starten.")
        return len(rows)
