"use client";

const ACCEPT = "image/jpeg,image/png,image/webp"; // iPhones wandeln HEIC dabei automatisch in JPEG um

/** Zwei große Flächen: Kamera öffnen oder Foto aus der Galerie wählen. */
export default function PhotoPicker({ onPick }: { onPick: (f: File | null) => void }) {
  return (
    <div className="pick">
      <label>
        <input type="file" accept={ACCEPT} capture="environment" onChange={(e) => onPick(e.target.files?.[0] ?? null)} />
        <span className="tile">
          <span className="ico"><svg viewBox="0 0 24 24"><path d="M4 8h3l2-2.5h6L17 8h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg></span>
          <span><b>Plan fotografieren</b><span>Kamera öffnet sich</span></span>
        </span>
      </label>
      <label>
        <input type="file" accept={ACCEPT} onChange={(e) => onPick(e.target.files?.[0] ?? null)} />
        <span className="tile">
          <span className="ico alt"><svg viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><path d="M3.5 16l5-5 4 4 3-3 5 5" /><circle cx="15.5" cy="9" r="1.5" /></svg></span>
          <span><b>Aus Fotos wählen</b><span>Foto oder Scan, JPEG oder PNG</span></span>
        </span>
      </label>
    </div>
  );
}

export function PhotoTips() {
  return (
    <ul className="tips">
      <li>Das Original gerade von oben fotografieren, bei gutem Licht und ohne Schatten.</li>
      <li>Alle Maßketten müssen im Bild sein, nur ein Grundriss pro Foto.</li>
      <li>Kopien mit Wasserzeichen und Bildschirmfotos sind oft zu klein zum Lesen.</li>
    </ul>
  );
}
