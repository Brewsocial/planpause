"""Mandantenfähige Ablage im Dateisystem.

Jeder Betrieb (Mandant) hat einen eigenen Ordner; ein Projekt kann nur über den
Mandanten erreicht werden, dem es gehört. Für den Produktivbetrieb wird diese
Klasse durch Postgres + Objektspeicher (z. B. S3 in einer EU-Region) ersetzt;
die Schnittstelle bleibt gleich.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

DATA = Path(os.environ.get("PLANPAUSE_DATA", Path(__file__).resolve().parents[1] / "data"))
SAFE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


class NotFound(Exception):
    pass


def _check(part: str) -> str:
    if not SAFE.match(part):
        raise NotFound(part)
    return part


class Store:
    def __init__(self, root: Path = DATA):
        self.root = root

    def _org(self, org: str) -> Path:
        return self.root / "orgs" / _check(org)

    def _proj(self, org: str, pid: str) -> Path:
        p = self._org(org) / "projects" / _check(pid)
        if not p.is_dir():
            raise NotFound(pid)
        return p

    # Mandanten ---------------------------------------------------------
    def orgs(self) -> dict:
        f = self.root / "orgs.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def ensure_org(self, org: str, name: str, api_key: str | None = None) -> str:
        orgs = self.orgs()
        if org not in orgs:
            orgs[org] = {"name": name, "api_key": api_key or secrets.token_urlsafe(24), "created": time.time()}
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / "orgs.json").write_text(json.dumps(orgs, indent=1))
        (self._org(org) / "projects").mkdir(parents=True, exist_ok=True)
        return orgs[org]["api_key"]

    def org_for_key(self, key: str) -> str | None:
        for org, d in self.orgs().items():
            if secrets.compare_digest(d["api_key"], key):
                return org
        return None

    # Projekte ----------------------------------------------------------
    def create(self, org: str, name: str) -> str:
        pid = "p" + secrets.token_hex(6)
        d = self._org(org) / "projects" / pid
        d.mkdir(parents=True)
        self.write_json(org, pid, "meta.json", {"id": pid, "name": name, "status": "neu", "created": time.time(), "updated": time.time()})
        return pid

    def list(self, org: str) -> list[dict]:
        base = self._org(org) / "projects"
        out = []
        for d in sorted(base.iterdir()) if base.exists() else []:
            m = d / "meta.json"
            if m.exists():
                out.append(json.loads(m.read_text()))
        return sorted(out, key=lambda m: -m.get("updated", 0))

    def meta(self, org: str, pid: str) -> dict:
        return self.read_json(org, pid, "meta.json")

    def update_meta(self, org: str, pid: str, **kw) -> dict:
        m = self.meta(org, pid)
        m.update(kw, updated=time.time())
        self.write_json(org, pid, "meta.json", m)
        return m

    def delete(self, org: str, pid: str) -> None:
        import shutil
        shutil.rmtree(self._proj(org, pid))

    def read_json(self, org: str, pid: str, name: str, default=None):
        f = self._proj(org, pid) / name
        if not f.exists():
            if default is not None:
                return default
            raise NotFound(name)
        return json.loads(f.read_text())

    def write_json(self, org: str, pid: str, name: str, data) -> None:
        f = self._proj(org, pid) / name
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(f)

    def write_bytes(self, org: str, pid: str, name: str, data: bytes) -> None:
        (self._proj(org, pid) / name).write_bytes(data)

    def path(self, org: str, pid: str, name: str) -> Path:
        f = self._proj(org, pid) / name
        if not f.exists():
            raise NotFound(name)
        return f

    def read_bytes(self, org: str, pid: str, name: str) -> bytes:
        return self.path(org, pid, name).read_bytes()

    def org_name(self, org: str) -> str:
        return self.orgs().get(org, {}).get("name", org)

    def user_for_token(self, token: str) -> dict | None:
        return None  # ohne Supabase keine Benutzerkonten, nur API-Schlüssel

    def org_for_user(self, user_id: str) -> str | None:
        return None

    def reset_stuck(self) -> int:
        n = 0
        for d in (self.root / "orgs").glob("*/projects/*/meta.json"):
            m = json.loads(d.read_text())
            if m.get("status") == "analyse":
                org, pid = d.parts[-4], d.parts[-2]
                self.update_meta(org, pid, status="fehler",
                                 error="Die Analyse wurde durch einen Neustart unterbrochen. Bitte erneut starten.")
                n += 1
        return n
