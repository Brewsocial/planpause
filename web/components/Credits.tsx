"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type Me } from "@/lib/api";

/** Guthaben des Betriebs und Kauf weiterer Grundrisse über Stripe Checkout. */
export default function Credits({ me, notice }: { me: Me; notice?: string }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const left = me.trial_left;
  if (left == null) return null;

  async function buy(pack: "einzel" | "zehn") {
    setBusy(pack); setErr("");
    try { window.location.href = (await api.checkout(pack)).url; }
    catch (x) { setErr((x as Error).message); setBusy(""); }
  }

  return (
    <div className="credits">
      <p className={left > 0 ? "hint" : "err"} style={{ margin: 0 }}>
        {left > 0 ? `Noch ${left} Grundriss${left === 1 ? "" : "e"} verfügbar.` : "Dein Guthaben ist aufgebraucht."}
        {notice && <> <b className="ok">{notice}</b></>}
      </p>
      {me.billing ? (
        <>
          <div className="credits-buy">
            <button type="button" className={`btn small${left > 0 ? "" : " primary"}`} disabled={!!busy} onClick={() => buy("einzel")}>
              {busy === "einzel" ? "Weiter zur Zahlung …" : "1 Grundriss kaufen · 4,99 €"}
            </button>
            <button type="button" className="btn small" disabled={!!busy} onClick={() => buy("zehn")}>
              {busy === "zehn" ? "Weiter zur Zahlung …" : "10 Grundrisse kaufen · 45 €"}
            </button>
          </div>
          <p className="hint" style={{ margin: 0, fontSize: 12 }}>
            Bezahlung über Stripe (Karte und weitere Zahlarten). Es gelten unsere <Link href="/agb">AGB</Link>.
            {me.billing_test && " Testmodus: Es wird nichts abgebucht."}
          </p>
        </>
      ) : left <= 0 && (
        <p className="hint" style={{ margin: 0 }}>Für weitere Grundrisse schreib uns an <a href={`mailto:${me.contact}`}>{me.contact}</a>.</p>
      )}
      {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
    </div>
  );
}
