"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type Crop = [number, number, number, number]; // Anteile der Seite: x0, y0, x1, y1
type Page = { page: number; mm: [number, number]; thumb: string };

/** PDF: Seite wählen und optional einen Ausschnitt aufziehen (z. B. Grundriss ohne Plankopf). */
export default function PdfSetup({ file, onChange }: { file: File; onChange: (v: { page: number; crop: Crop | null }) => void }) {
  const [pages, setPages] = useState<Page[] | null>(null);
  const [err, setErr] = useState("");
  const [page, setPage] = useState(1);
  const [crop, setCrop] = useState<Crop | null>(null);

  useEffect(() => {
    setPages(null); setErr("");
    api.pdfPages(file).then((r) => { setPages(r.pages); setPage(1); setCrop(null); }).catch((e) => setErr(e.message));
  }, [file]);
  useEffect(() => { onChange({ page, crop }); }, [page, crop]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <p className="err" style={{ margin: 0 }}>{err}</p>;
  if (!pages) return <p className="muted" style={{ margin: 0 }}>PDF wird gelesen …</p>;
  const current = pages.find((p) => p.page === page) ?? pages[0];

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {pages.length > 1 && (<>
        <span className="hint">{pages.length} Seiten. Tippe die Seite mit dem Grundriss an:</span>
        <div className="pdf-pages">
          {pages.map((p) => (
            <button type="button" key={p.page} className={`pdf-page${p.page === page ? " on" : ""}`} onClick={() => { setPage(p.page); setCrop(null); }}>
              <img src={p.thumb} alt={`Seite ${p.page}`} /><span>Seite {p.page}</span>
            </button>))}
        </div>
      </>)}
      <span className="hint">
        Seite {current.page} · {current.mm[0]} × {current.mm[1]} mm. Optional: Ausschnitt mit dem Finger aufziehen, z. B. nur der Grundriss ohne Plankopf und Legende.
      </span>
      <CropBox src={current.thumb} crop={crop} onCrop={setCrop} />
      {crop && <div><button type="button" className="btn small" onClick={() => setCrop(null)}>Ganze Seite verwenden</button></div>}
    </div>
  );
}

function CropBox({ src, crop, onCrop }: { src: string; crop: Crop | null; onCrop: (c: Crop | null) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const start = useRef<[number, number] | null>(null);
  const [draft, setDraft] = useState<Crop | null>(null);
  const at = (e: React.PointerEvent): [number, number] => {
    const r = box.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  const norm = (a: [number, number], b: [number, number]): Crop => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  const shown = draft ?? crop;
  return (
    <div ref={box} className="cropbox"
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); start.current = at(e); setDraft(null); }}
      onPointerMove={(e) => { if (start.current) setDraft(norm(start.current, at(e))); }}
      onPointerUp={(e) => {
        if (start.current) {
          const c = norm(start.current, at(e));
          onCrop(c[2] - c[0] > 0.05 && c[3] - c[1] > 0.05 ? c : null);  // nur Antippen: kein Ausschnitt
        }
        start.current = null; setDraft(null);
      }}>
      <img src={src} alt="PDF-Seite" draggable={false} />
      {shown && <div className="crop-rect" style={{ left: `${shown[0] * 100}%`, top: `${shown[1] * 100}%`,
        width: `${(shown[2] - shown[0]) * 100}%`, height: `${(shown[3] - shown[1]) * 100}%` }} />}
    </div>
  );
}
