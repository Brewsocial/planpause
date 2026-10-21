"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

type Mode = "login" | "link" | "reset" | "setpw";

export default function Login() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!supabase) { window.location.href = "/"; return; }
    // Einladungs- und Zurücksetzen-Links führen hierher zurück: Passwort festlegen
    const setpw = new URLSearchParams(window.location.search).has("setpw");
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY" || (setpw && session)) setMode("setpw");
    });
    supabase.auth.getSession().then(({ data: s }) => {
      if (s.session) { if (setpw) setMode("setpw"); else window.location.href = "/"; }
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const back = `${typeof window === "undefined" ? "" : window.location.origin}/login?setpw=1`;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true); setErr(""); setMsg("");
    const a = supabase.auth;
    const r =
      mode === "login" ? await a.signInWithPassword({ email, password: pw }) :
      mode === "link" ? await a.signInWithOtp({ email, options: { shouldCreateUser: false, emailRedirectTo: window.location.origin } }) :
      mode === "reset" ? await a.resetPasswordForEmail(email, { redirectTo: back }) :
      await a.updateUser({ password: pw });
    setBusy(false);
    if (r.error) {
      setErr(r.error.message === "Invalid login credentials" ? "E-Mail oder Passwort stimmt nicht." :
             r.error.message.includes("Signups not allowed") ? "Für diese E-Mail gibt es keinen Zugang. Planpause ist derzeit nur auf Einladung nutzbar." :
             r.error.message);
      return;
    }
    if (mode === "login" || mode === "setpw") window.location.href = "/";
    else setMsg("Wir haben dir eine E-Mail geschickt. Bitte den Link darin öffnen.");
  }

  const title = { login: "Anmelden", link: "Anmelden per E-Mail-Link", reset: "Passwort vergessen", setpw: "Passwort festlegen" }[mode];
  const button = { login: "Anmelden", link: "Link senden", reset: "Link zum Zurücksetzen senden", setpw: "Passwort speichern" }[mode];

  return (
    <main>
      <form className="sheet auth" onSubmit={submit}>
        <div>
          <h1 style={{ fontSize: 30 }}>{title}</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            {mode === "setpw" ? "Mindestens 8 Zeichen. Danach meldest du dich mit E-Mail und Passwort an." :
             "Planpause ist in der Testphase und nur auf Einladung nutzbar."}
          </p>
        </div>
        {mode !== "setpw" && (
          <label className="field">E-Mail<input type="text" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        )}
        {(mode === "login" || mode === "setpw") && (
          <label className="field">{mode === "setpw" ? "Neues Passwort" : "Passwort"}
            <input type="password" autoComplete={mode === "setpw" ? "new-password" : "current-password"} minLength={mode === "setpw" ? 8 : undefined}
              value={pw} onChange={(e) => setPw(e.target.value)} required />
          </label>
        )}
        <button className="btn primary big" disabled={busy}>{button}</button>
        {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
        {msg && <p style={{ margin: 0 }}>{msg}</p>}
        {mode !== "setpw" && (
          <div className="links">
            {mode !== "login" && <a href="#" onClick={(e) => { e.preventDefault(); setMode("login"); }}>Mit Passwort anmelden</a>}
            {mode !== "link" && <a href="#" onClick={(e) => { e.preventDefault(); setMode("link"); }}>Link per E-Mail</a>}
            {mode !== "reset" && <a href="#" onClick={(e) => { e.preventDefault(); setMode("reset"); }}>Passwort vergessen</a>}
          </div>
        )}
      </form>
    </main>
  );
}
