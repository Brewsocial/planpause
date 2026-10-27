import type { Metadata } from "next";
import { CadPlan, PaperPlan } from "@/components/PlanSketch";
import { SITE_URL } from "@/lib/site";

const TITLE = "Grundriss digitalisieren: Foto oder PDF in DXF umwandeln";
const DESCRIPTION =
  "Planpause macht aus alten Papiergrundrissen maßhaltige DXF-Dateien. Foto, Scan oder PDF hochladen: Wände, Fenster, Türen und Räume werden aus den Maßketten berechnet, nicht nur abgepaust. In Minuten statt Stunden.";

export const metadata: Metadata = {
  title: { absolute: `Planpause · ${TITLE}` },
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: { type: "website", locale: "de_DE", url: "/", siteName: "Planpause", title: TITLE, description: DESCRIPTION },
};

const TRY = "/registrieren";

const STEPS = [
  { t: "Plan hochladen", d: "Foto vom Papierplan, Scan oder PDF. Beim PDF wählst du Seite und Ausschnitt, beim Handy reicht ein Foto direkt von der Baustelle." },
  { t: "Maßketten auswerten", d: "Planpause liest jede Maßzahl, rechnet die Ketten gegeneinander und legt Wände, Öffnungen und Räume daraus fest. Das dauert einige Minuten." },
  { t: "Prüfen und als DXF laden", d: "Das Ergebnis liegt deckungsgleich über deinem Original. Unstimmige Maße sind markiert. Dann als DXF in dein CAD." },
];

const COMPARE: [string, string, string][] = [
  ["Grundlage", "Linien im Bild werden nachgefahren", "Jede Maßzahl der Maßketten wird gelesen"],
  ["Maßstab", "Geschätzt, Fotoverzerrung geht ins Ergebnis", "Aus den Maßketten berechnet und ausgeglichen"],
  ["Fehler im Plan", "Bleiben unbemerkt", "Widersprüche werden gefunden und markiert"],
  ["Ergebnis", "Bild oder Vektorgrafik", "DXF mit Layern, Bemaßung und Raumflächen"],
];

const DXF_LAYERS = ["WAENDE", "FENSTER", "TUEREN", "RAEUME mit m²", "BEMASSUNG", "TREPPE", "PRUEFPUNKTE"];

const AUDIENCE = [
  { t: "Handwerk", d: "Trockenbau, Elektro, Sanitär, Maler, Bodenleger: Angebot und Materialbedarf auf Basis echter Maße statt Handskizze." },
  { t: "Energieberatung", d: "Bestandsgebäude schnell als Zeichnung für Flächen, Hüllflächen und Sanierungsfahrplan." },
  { t: "Planung im Bestand", d: "Architektur- und Ingenieurbüros sparen das Abzeichnen alter Bauakten und starten direkt im CAD." },
  { t: "Gutachten und Verwaltung", d: "Sachverständige und Hausverwaltungen bringen Papierakten in ein bearbeitbares, maßhaltiges Format." },
];

const FAQ: [string, string][] = [
  ["Welche Pläne kann ich hochladen?",
    "Fotos (JPG, PNG, WebP), Scans und PDF-Dateien. Am besten funktionieren bemaßte Grundrisse aus Bauakten, Bauanträgen oder Exposés. Ein gerade aufgenommenes Handyfoto reicht, wenn die Maßzahlen lesbar sind."],
  ["Wie genau ist das Ergebnis?",
    "So genau wie die Bemaßung im Plan. Planpause übernimmt die Maße aus den Maßketten und gleicht sie gegeneinander ab. Kanten ohne Maß werden aus der Zeichnung abgeleitet und als geschätzt gekennzeichnet. Eine Ampel zeigt dir auf einen Blick, wie belastbar der Plan ist."],
  ["Was passiert, wenn Maße im Plan nicht zusammenpassen?",
    "Widersprüchliche Maßketten werden erkannt und im Ergebnis markiert, statt still übernommen zu werden. Du siehst genau, welche Stelle du vor Ort nachmessen solltest."],
  ["In welchem Format bekomme ich den Grundriss?",
    "Als DXF in Millimetern, mit getrennten Layern für Wände, Fenster, Türen, Räume mit Fläche, Bemaßung und Prüfpunkte. DXF öffnen alle gängigen CAD-Programme, etwa AutoCAD, BricsCAD, ArchiCAD, Vectorworks oder DraftSight."],
  ["Mein Gebäude ist auf mehrere Zeichnungen verteilt. Geht das?",
    "Ja. Ein Projekt fasst alle Pläne eines Gebäudes zusammen. Mehrere Zeichnungen desselben Geschosses, etwa Altbau und Anbau, schiebst du einfach aneinander. Sie rasten an den Außenecken ein und lassen sich als ein gemeinsames DXF exportieren."],
  ["Was kostet ein Grundriss?",
    "Zum Einführungspreis 20 € pro Grundriss, im 10er-Paket 179 €. Als Kleinunternehmer weisen wir keine Umsatzsteuer aus, die Preise sind Endpreise."],
  ["Ersetzt Planpause das Aufmaß vor Ort?",
    "Nein. Planpause macht aus einem vorhandenen Plan eine saubere Arbeitsgrundlage. Wo der Plan nichts hergibt oder sich widerspricht, zeigt Planpause das offen an, damit du gezielt nachmessen kannst."],
  ["Wie bekomme ich Zugang?",
    "Über „Jetzt ausprobieren“ legst du in einer Minute ein Konto für deinen Betrieb an und kannst direkt dein erstes Projekt erstellen. Die ersten zwei Grundrisse sind kostenlos."],
];

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication", name: "Planpause", url: SITE_URL, applicationCategory: "DesignApplication",
      operatingSystem: "Web", inLanguage: "de", description: DESCRIPTION,
      publisher: { "@type": "Organization", name: "KiCO" },
      offers: { "@type": "Offer", price: "20.00", priceCurrency: "EUR", description: "Einführungspreis pro Grundriss" },
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
    },
  ],
};

export default function Landing() {
  return (
    <main className="lp">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <section className="lp-hero">
        <div className="lp-hero-text">
          <p className="lp-kicker">Bestandsgrundrisse digitalisieren</p>
          <h1>Vom Papierplan zur maßhaltigen DXF. In Minuten.</h1>
          <p className="lead">
            Foto, Scan oder PDF hochladen. Planpause liest die Maßketten, berechnet daraus jede Wand und liefert dir
            eine DXF, mit der du im CAD sofort weiterarbeiten kannst.
          </p>
          <div className="lp-cta">
            <a className="btn primary big" href={TRY}>Jetzt ausprobieren</a>
            <a className="btn ghost big" href="#so-gehts">So funktioniert es</a>
          </div>
          <ul className="lp-facts">
            <li><b>Minuten</b> statt Stunden Nachzeichnen</li>
            <li><b>Maßketten</b> statt Pixelschätzung</li>
            <li><b>DXF</b> mit Layern und Bemaßung</li>
          </ul>
        </div>
        <div className="lp-visual">
          <figure className="lp-card lp-paper"><PaperPlan /><figcaption>Foto vom Papierplan</figcaption></figure>
          <figure className="lp-card lp-cad"><CadPlan /><figcaption>DXF aus den Maßketten</figcaption></figure>
        </div>
      </section>

      <section className="lp-sec">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Das Problem</p>
          <h2>Bestandspläne liegen auf Papier. Nachzeichnen kostet Stunden.</h2>
          <p className="lead">
            Für Angebot, Umbau oder Energieberatung brauchst du den Grundriss im CAD. Vorhanden ist aber meist nur die
            alte Bauakte, ein Exposé oder ein Foto davon. Jede Wand von Hand abzeichnen bindet Zeit, die auf der
            Baustelle oder im Büro fehlt.
          </p>
        </div>
        <div className="lp-stats">
          <div className="sheet lp-stat"><b>85 %</b><span>weniger Zeitaufwand</span></div>
          <div className="sheet lp-stat"><b>60 %</b><span>geringere Kosten</span></div>
          <p className="hint lp-stat-note">Im Vergleich zum Nachzeichnen von Hand, Schätzung pro Geschoss: von Hand rund 1,5 bis 2,5 Stunden, bei 60 € Stundensatz etwa 110 €. Mit Planpause 20 € plus rund 15 Minuten zum Prüfen. Abhängig von Plan und Größe.</p>
        </div>
      </section>

      <section className="lp-sec" id="unterschied">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Der Unterschied</p>
          <h2>Gemessen, nicht abgepaust.</h2>
          <p className="lead">
            Viele Werkzeuge fahren die Linien im Bild nach. Dann landen schiefe Fotos, verzogene Scans und
            Kopierfehler direkt in deiner Zeichnung. Planpause geht vor wie ein Bauzeichner: Die KI liest jede
            Maßzahl, die Geometrie wird aus den Maßketten berechnet.
          </p>
        </div>
        <div className="sheet lp-compare" role="table" aria-label="Vergleich">
          <div className="lp-row lp-row-hd" role="row">
            <span role="columnheader" />
            <span role="columnheader">Bild nachzeichnen</span>
            <span role="columnheader">Planpause</span>
          </div>
          {COMPARE.map(([k, a, b]) => (
            <div className="lp-row" role="row" key={k}>
              <span role="rowheader">{k}</span>
              <span role="cell" className="lp-them">{a}</span>
              <span role="cell" className="lp-us">{b}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-sec" id="so-gehts">
        <div className="lp-sec-hd">
          <p className="lp-kicker">So geht&apos;s</p>
          <h2>Drei Schritte bis zur DXF.</h2>
        </div>
        <ol className="lp-steps">
          {STEPS.map((s, i) => (
            <li className="sheet" key={s.t}>
              <span className="lp-num">{i + 1}</span>
              <h3>{s.t}</h3>
              <p>{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="lp-sec lp-split">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Das bekommst du</p>
          <h2>Eine DXF, die sich wie gezeichnet anfühlt.</h2>
          <p className="lead">
            Keine Bilddatei mit Linien, sondern eine saubere Zeichnung in Millimetern: Wände als geschlossene Flächen,
            Fenster, Türen mit Aufschlag, Räume mit Name und Fläche, die Maßketten als echte Bemaßung.
          </p>
          <ul className="lp-chips">{DXF_LAYERS.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
        <ul className="lp-list">
          <li><b>Qualitätsampel.</b> Grün, Gelb oder Rot zeigt, wie belastbar der Plan ist und wo nachgemessen werden sollte.</li>
          <li><b>Kontrolle über dem Original.</b> Das Ergebnis liegt deckungsgleich auf deinem Plan, ein Regler blendet zwischen beiden.</li>
          <li><b>Projekte statt Einzeldateien.</b> Alle Geschosse eines Hauses gebündelt, mehrere Zeichnungen pro Geschoss zusammensetzbar.</li>
          <li><b>Auch ohne Maße.</b> Fehlt die Bemaßung, liefert Planpause trotzdem eine Zeichnung und sagt dir deutlich, dass der Maßstab geschätzt ist.</li>
          <li><b>Am Handy nutzbar.</b> Plan fotografieren, hochladen, später am Rechner als DXF weiterverarbeiten.</li>
        </ul>
      </section>

      <section className="lp-sec" id="preise">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Preise</p>
          <h2>Bezahlt wird pro Grundriss. Ohne Abo.</h2>
          <p className="lead">Ein Grundriss ist eine Zeichnung, meist ein Geschoss. Du zahlst nur, was du digitalisierst.</p>
        </div>
        <div className="lp-prices">
          <div className="sheet lp-price">
            <p className="lp-badge">Einführungspreis</p>
            <h3>Einzelner Grundriss</h3>
            <p className="lp-amount"><b>20 €</b><span>pro Grundriss</span></p>
            <ul>
              <li>Auswertung der Maßketten</li>
              <li>DXF mit Layern und Bemaßung</li>
              <li>Prüfbericht mit markierten Unstimmigkeiten</li>
              <li>Geschosse zusammensetzen</li>
            </ul>
          </div>
          <div className="sheet lp-price lp-price-hi">
            <p className="lp-badge">Für Betriebe</p>
            <h3>10er-Paket</h3>
            <p className="lp-amount"><b>179 €</b><span>rund 18 € pro Grundriss</span></p>
            <ul>
              <li>Alles aus dem Einzelpreis</li>
              <li>Für beliebige Projekte nutzbar</li>
              <li>Rund 10 % günstiger als einzeln</li>
            </ul>
          </div>
        </div>
        <p className="hint">Endpreise, keine Umsatzsteuer nach § 19 UStG. Zum Ausprobieren sind die ersten zwei Grundrisse kostenlos.</p>
      </section>

      <section className="lp-sec">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Für wen</p>
          <h2>Für alle, die mit Bestand arbeiten.</h2>
        </div>
        <div className="lp-grid">
          {AUDIENCE.map((a) => (
            <div className="sheet lp-tile" key={a.t}><h3>{a.t}</h3><p>{a.d}</p></div>
          ))}
        </div>
      </section>

      <section className="lp-sec" id="fragen">
        <div className="lp-sec-hd">
          <p className="lp-kicker">Fragen</p>
          <h2>Häufige Fragen</h2>
        </div>
        <div className="sheet lp-faq">
          {FAQ.map(([q, a]) => (
            <details key={q}><summary>{q}</summary><p>{a}</p></details>
          ))}
        </div>
      </section>

      <section className="sheet lp-final">
        <h2>Schick uns deinen nächsten Bestandsplan.</h2>
        <p className="lead">Konto anlegen, Projekt erstellen, Plan hochladen. Die ersten zwei Grundrisse sind kostenlos.</p>
        <div className="lp-cta">
          <a className="btn primary big" href={TRY}>Jetzt ausprobieren</a>
          <a className="btn big" href="/login">Ich habe schon ein Konto</a>
        </div>
      </section>
    </main>
  );
}
