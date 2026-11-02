"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let cached: Promise<boolean> | null = null;

/** Privatkunde (Verbraucher)? Dann braucht jede Auswertung die Zustimmung zum vorzeitigen Beginn. */
export function usePrivate(): boolean {
  const [priv, setPriv] = useState(false);
  useEffect(() => {
    cached ??= api.me().then((m) => !!m.private).catch(() => false);
    cached.then(setPriv);
  }, []);
  return priv;
}

/** Ausdrückliche Zustimmung und Bestätigung nach § 356 Abs. 4 und 5 BGB, siehe AGB § 9. */
export function Waiver({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="check waiver">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} required />
      <span>Die Auswertung soll sofort beginnen. Mir ist bekannt, dass mein{" "}
        <Link href="/agb#widerruf" target="_blank">Widerrufsrecht</Link> damit erlischt.</span>
    </label>
  );
}
