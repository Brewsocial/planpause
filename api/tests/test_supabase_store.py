"""SupabaseStore gegen eine nachgebaute Supabase-REST-Schnittstelle (ohne Netz)."""
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

USER = {"id": "11111111-1111-1111-1111-111111111111", "email": "test@example.com"}


class FakeSupabase:
    def __init__(self):
        self.tables = {"orgs": [], "org_members": [], "projects": []}
        self.objects: dict[str, bytes] = {}
        self.users: dict[str, dict] = {}

    def _match(self, row, params):
        for k, v in params.items():
            if k == "select":
                continue
            op, val = v.split(".", 1)
            assert op in ("eq", "gte")
            got = row["meta"].get(k.split("->>")[1]) if "->>" in k else row.get(k)
            if op == "gte":
                if got is not None and str(got) < val:  # ohne created_at: gerade angelegt
                    return False
            elif str(got) != val:
                return False
        return True

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, params = req.url.path, dict(req.url.params)
        if path == "/auth/v1/user":
            ok = req.headers.get("authorization") == "Bearer gutes-token"
            return httpx.Response(200 if ok else 401, json=USER if ok else {})
        if path == "/auth/v1/admin/users" and req.method == "POST":
            body = json.loads(req.content)
            if any(u["email"] == body["email"] for u in self.users.values()):
                return httpx.Response(422, json={"msg": "A user with this email address has already been registered"})
            u = {"id": f"00000000-0000-0000-0000-{len(self.users) + 1:012d}", "email": body["email"]}
            self.users[u["id"]] = u
            return httpx.Response(200, json=u)
        if m := re.fullmatch(r"/auth/v1/admin/users/(.+)", path):
            self.users.pop(m[1], None)
            return httpx.Response(200, json={})
        if m := re.fullmatch(r"/rest/v1/(\w+)", path):
            rows = self.tables[m[1]]
            profile = req.headers.get("accept-profile" if req.method == "GET" else "content-profile")
            assert profile == "planpause", f"{req.method} {path} ohne Schema planpause"
            if req.method == "GET":
                return httpx.Response(200, json=[r for r in rows if self._match(r, params)])
            if req.method == "POST":
                body = json.loads(req.content)
                key = "user_id" if m[1] == "org_members" else "id"
                if not any(r[key] == body[key] for r in rows):
                    rows.append(body)
                return httpx.Response(201)
            if req.method == "PATCH":
                hit = [r for r in rows if self._match(r, params)]
                for r in hit:
                    r.update(json.loads(req.content))
                if "return=representation" in req.headers.get("prefer", ""):
                    return httpx.Response(200, json=hit)
                return httpx.Response(204)
            if req.method == "DELETE":
                self.tables[m[1]] = [r for r in rows if not self._match(r, params)]
                return httpx.Response(204)
        if path == "/storage/v1/object/list/planpause":
            prefix = json.loads(req.content)["prefix"]
            return httpx.Response(200, json=[{"name": k[len(prefix):]} for k in self.objects if k.startswith(prefix)])
        if path == "/storage/v1/object/planpause" and req.method == "DELETE":
            for k in json.loads(req.content)["prefixes"]:
                self.objects.pop(k, None)
            return httpx.Response(200, json=[])
        if m := re.fullmatch(r"/storage/v1/object/planpause/(.+)", path):
            if req.method == "POST":
                self.objects[m[1]] = req.content
                return httpx.Response(200, json={})
            if m[1] in self.objects:
                return httpx.Response(200, content=self.objects[m[1]])
            return httpx.Response(400, json={"error": "not_found"})
        raise AssertionError(f"unerwartet: {req.method} {path}")


@pytest.fixture
def sb(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test")
    monkeypatch.setenv("PLANPAUSE_DATA", str(tmp_path))
    import importlib
    import app.main as main
    importlib.reload(main)
    fake = FakeSupabase()
    main.store.http = httpx.Client(base_url="https://fake.supabase.co", transport=httpx.MockTransport(fake),
                                   headers=main.store.http.headers)
    with TestClient(main.app) as c:
        yield c, fake, main
    monkeypatch.delenv("SUPABASE_URL")
    importlib.reload(main)


H = {"Authorization": "Bearer gutes-token"}


def test_ohne_betrieb_403_und_falsches_token_401(sb):
    c, fake, _ = sb
    assert c.get("/projects", headers=H).status_code == 403
    assert c.get("/projects", headers={"Authorization": "Bearer demo-schluessel"}).status_code == 401


def test_projektablauf_mit_supabase(sb):
    c, fake, main = sb
    main.store.ensure_org("malerbetrieb-mueller", "Malerbetrieb Müller")
    fake.tables["org_members"].append({"user_id": USER["id"], "org_id": "malerbetrieb-mueller"})
    assert c.get("/me", headers=H).json() | {"contact": ""} == {"org": "malerbetrieb-mueller", "name": "Malerbetrieb Müller", "trial_left": None, "contact": ""}

    pid = c.post("/projects/demo/darmstaedter14", headers=H).json()["id"]
    assert [p["id"] for p in c.get("/projects", headers=H).json()] == [pid]
    assert c.get(f"/projects/{pid}", headers=H).json()["result"]["stats"]["conflicts"] == 2
    assert c.get(f"/projects/{pid}/image", headers=H).content[:2] == b"\xff\xd8"
    assert b"SECTION" in c.get(f"/projects/{pid}/export/dxf", headers=H).content[:200]

    fake.tables["org_members"][0]["org_id"] = "anderer-betrieb"
    assert c.get(f"/projects/{pid}", headers=H).status_code == 404
    fake.tables["org_members"][0]["org_id"] = "malerbetrieb-mueller"

    assert c.delete(f"/projects/{pid}", headers=H).status_code == 200
    assert fake.objects == {} and [r["meta"]["kind"] for r in fake.tables["projects"]] == ["folder"]  # Beispiel-Ordner bleibt
    fid = fake.tables["projects"][0]["id"]
    assert c.get("/folders", headers=H).json()["folders"][0]["plans"] == []
    assert c.delete(f"/folders/{fid}", headers=H).status_code == 200
    assert fake.tables["projects"] == []


def test_neustart_setzt_haengende_analyse_zurueck(sb):
    c, fake, main = sb
    main.store.ensure_org("betrieb-a", "A")
    pid = main.store.create("betrieb-a", "Plan")
    main.store.update_meta("betrieb-a", pid, status="analyse")
    assert main.store.reset_stuck() == 1
    assert main.store.meta("betrieb-a", pid)["status"] == "fehler"


def test_selbst_registrierung_legt_konto_und_probebetrieb_an(sb):
    c, fake, main = sb
    neu = {"email": " Info@Maler-Huber.de ", "password": "geheim123", "company": "Malerbetrieb Hüber GmbH", "business": True}
    assert c.post("/signup", json={**neu, "business": False}).status_code == 400
    assert c.post("/signup", json={**neu, "password": "kurz"}).status_code == 400
    r = c.post("/signup", json=neu, headers={"X-Planpause-Client-IP": "1.2.3.4"})
    assert r.status_code == 200, r.text
    org = r.json()["org"]
    assert org.startswith("malerbetrieb-hueber-gmbh-")
    assert [u["email"] for u in fake.users.values()] == ["info@maler-huber.de"]
    assert fake.tables["orgs"] == [{"id": org, "name": "Malerbetrieb Hüber GmbH", "trial_left": main.TRIAL_ANALYSES}]
    assert fake.tables["org_members"][0]["org_id"] == org
    assert c.post("/signup", json=neu).status_code == 409  # gleiche E-Mail
    assert len(fake.tables["orgs"]) == 1


def test_registrierung_begrenzt(sb, monkeypatch):
    c, fake, main = sb
    monkeypatch.setattr(main, "SIGNUPS_PER_DAY", 1)
    ok = lambda i: {"email": f"a{i}@b.de", "password": "geheim123", "company": f"Betrieb {i}", "business": True}  # noqa: E731
    assert c.post("/signup", json=ok(1)).status_code == 200
    assert c.post("/signup", json=ok(2)).status_code == 429  # Tagesgrenze
    monkeypatch.setattr(main, "SIGNUPS_PER_DAY", 99)
    ip = {"X-Planpause-Client-IP": "9.9.9.9"}
    assert [c.post("/signup", json=ok(i), headers=ip).status_code for i in range(3, 7)] == [200, 200, 200, 429]
