import Link from "next/link";

export const metadata = { title: "Seite nicht gefunden" };

export default function NotFound() {
  return (
    <main>
      <div className="sheet empty">
        <h1 style={{ fontSize: 30 }}>Seite nicht gefunden</h1>
        <p>Diese Adresse gibt es bei Planpause nicht (mehr).</p>
        <p><Link className="btn primary" href="/">Zur Startseite</Link></p>
      </div>
    </main>
  );
}
