"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const PUBLIC = ["/", "/login", "/registrieren", "/impressum", "/datenschutz"];

/** Leitet ohne Anmeldung zur Login-Seite und zeigt den Betrieb im Kopf an. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const open = PUBLIC.includes(path);
  const [ready, setReady] = useState(!supabase || open);
  const [denied, setDenied] = useState("");

  useEffect(() => {
    if (!supabase || open) { setReady(true); return; }
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) { router.replace("/login"); return; }
      // Das Supabase-Projekt kann Konten anderer Apps enthalten: Zugang nur mit Betrieb
      api.me().then(() => setReady(true)).catch((e: Error) => setDenied(e.message));
    });
  }, [open, router]);

  if (denied) return (
    <main className="sheet auth">
      <h2>Kein Zugang zu Planpause</h2>
      <p className="muted">{denied} Für ein eigenes Konto bitte abmelden und unter „Jetzt ausprobieren“ registrieren.</p>
      <button className="btn" onClick={() => supabase?.auth.signOut().then(() => { window.location.href = "/login"; })}>Abmelden</button>
    </main>
  );
  return ready ? <>{children}</> : <p className="muted">Lade …</p>;
}

export function Account() {
  const path = usePathname();
  const [org, setOrg] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (PUBLIC.includes(path)) return;
    api.me().then((m) => setOrg(m.name)).catch(() => setOrg(""));
    supabase?.auth.getSession().then(({ data }) => setEmail(data.session?.user.email ?? ""));
  }, [path]);

  async function logout() {
    await supabase?.auth.signOut();
    window.location.href = "/login";
  }

  if (path === "/login") return null;
  if (PUBLIC.includes(path)) return <SignIn />;
  return (
    <span className="org">
      <span className="who">{org}{email && <span className="mail"> · {email}</span>}</span>
      {supabase && <button className="btn small" onClick={logout}>Abmelden</button>}
    </span>
  );
}

/** Auf öffentlichen Seiten: Einstieg in die App, je nach Anmeldung */
function SignIn() {
  const [inApp, setInApp] = useState(!supabase);
  useEffect(() => { supabase?.auth.getSession().then(({ data }) => setInApp(!!data.session)); }, []);
  return <a className="btn small primary" href={inApp ? "/projekte" : "/login"}>{inApp ? "Meine Projekte" : "Anmelden"}</a>;
}
