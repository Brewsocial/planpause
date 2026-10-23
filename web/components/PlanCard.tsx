"use client";

import Link from "next/link";
import Thumb from "@/components/Thumb";
import { statusBadge } from "@/lib/status";
import type { Meta } from "@/lib/types";

export default function PlanCard({ p }: { p: Meta }) {
  const [label, cls] = statusBadge(p);
  return (
    <Link href={`/grundriss?id=${p.id}`} className="sheet card">
      <div className="thumb"><Thumb id={p.id} /></div>
      <div className="info">
        <h3>{p.part ? `${p.part}` : p.name}</h3>
        {p.part && <span className="hint" style={{ marginTop: -4 }}>{p.name}</span>}
        <div className="badges"><span className={`badge ${cls}`}>{label}</span>{p.demo && <span className="badge">Beispiel</span>}</div>
      </div>
    </Link>
  );
}
