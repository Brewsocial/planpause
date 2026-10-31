"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

/** Selbst-Registrierung: Konto und eigener Betrieb mit kostenlosen Probe-Grundrissen, danach direkt zum ersten Projekt. */
export default function Register() {
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [business, setBusiness] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.signup({ company, email, password: pw, business });
      if (supabase) {
        const r = await supabase.auth.signInWithPassword({ email: email.trim().toLowerCase(), password: pw });
        if (r.error) throw new Error("Dein Konto ist angelegt. Bitte melde dich jetzt an.");
      }
      window.location.href = "/projekte?neu=1";
    } catch (x) {
      setErr((x as Error).message);
      setBusy(false);
    }
  }

  return (
    <main>
      <form className="sheet auth" onSubmit={submit}>
        <div>
          <h1 style={{ fontSize: 30 }}>Planpause ausprobieren</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            Konto anlegen, Projekt erstellen, ersten Grundriss hochladen.
          </p>
        </div>
        <label className="field">Name deines Betriebs
          <input type="text" autoComplete="organization" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="z. B. Malerbetrieb Müller" required minLength={2} maxLength={80} />
        </label>
        <label className="field">E-Mail
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">Passwort
          <input type="password" autoComplete="new-password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} required />
          <span className="hint">Mindestens 8 Zeichen</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={business} onChange={(e) => setBusiness(e.target.checked)} required />
          <span>Ich nutze Planpause gewerblich. Die <Link href="/datenschutz" target="_blank">Datenschutzerklärung</Link> habe ich gelesen.</span>
        </label>
        <button className="btn primary big" disabled={busy}>{busy ? "Konto wird angelegt …" : "Konto anlegen"}</button>
        {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
        <div className="links"><Link href="/login">Ich habe schon ein Konto</Link></div>
      </form>
    </main>
  );
}
