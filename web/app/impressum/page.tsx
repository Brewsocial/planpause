import { LEGAL } from "@/lib/legal";

export const metadata = { title: "Impressum · Planpause" };

export default function Impressum() {
  return (
    <main className="sheet legal">
      <h1>Impressum</h1>
      <p>Angaben gemäß § 5 DDG und § 18 Abs. 2 MStV</p>

      <h3>Diensteanbieter</h3>
      <p>{LEGAL.legalName}<br />{LEGAL.street}<br />{LEGAL.zipCity}<br />{LEGAL.country}</p>

      <h3>Kontakt</h3>
      <p>Telefon: {LEGAL.phone}<br />E-Mail: <a href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a></p>

      <h3>Umsatzsteuer</h3>
      <p>{LEGAL.vat}</p>

      <h3>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV</h3>
      <p>{LEGAL.name} (Anschrift wie oben)</p>

      <h2>Streitschlichtung</h2>
      <p>Die Europäische Kommission hat die Plattform zur Online-Streitbeilegung (ODR) zum 20. Juli 2025 eingestellt; ein Link
        wird daher nicht mehr angegeben.</p>
      <p>Wir sind nicht bereit oder verpflichtet, an Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.</p>

      <h2>Haftung für Inhalte</h2>
      <p>Als Diensteanbieter sind wir gemäß § 7 Abs. 1 DDG für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen
        verantwortlich. Nach §§ 8 bis 10 DDG sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder gespeicherte
        fremde Informationen zu überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige Tätigkeit hinweisen.</p>
      <p>Verpflichtungen zur Entfernung oder Sperrung der Nutzung von Informationen nach den allgemeinen Gesetzen bleiben hiervon
        unberührt. Eine diesbezügliche Haftung ist jedoch erst ab dem Zeitpunkt der Kenntnis einer konkreten Rechtsverletzung
        möglich. Bei Bekanntwerden entsprechender Rechtsverletzungen werden wir diese Inhalte umgehend entfernen.</p>

      <h2>Haftung für die Ergebnisse</h2>
      <p>{LEGAL.product} erstellt digitale Grundrisse automatisch aus Fotos, Scans und PDFs, teilweise mit Hilfe künstlicher
        Intelligenz. Die Ergebnisse können trotz sorgfältiger Auswertung Fehler enthalten, etwa falsch gelesene Maße, fehlende oder
        falsch zugeordnete Bauteile oder Abweichungen vom tatsächlichen Bestand. Sie ersetzen kein Aufmaß vor Ort.</p>
      <p>Maße und Inhalte sind vor jeder Verwendung, insbesondere für Planung, Kalkulation, Bestellung oder Ausführung,
        eigenverantwortlich zu prüfen. Für Fehler in den erstellten Grundrissen und für Schäden, die aus ihrer Verwendung entstehen,
        übernehmen wir keine Haftung, soweit dies gesetzlich zulässig ist. Unberührt bleibt die Haftung für Vorsatz und grobe
        Fahrlässigkeit, für Schäden aus der Verletzung von Leben, Körper oder Gesundheit sowie nach dem Produkthaftungsgesetz.</p>

      <h2>Haftung für Links</h2>
      <p>Unser Angebot enthält ggf. Links zu externen Websites Dritter, auf deren Inhalte wir keinen Einfluss haben. Deshalb können
        wir für diese fremden Inhalte auch keine Gewähr übernehmen. Für die Inhalte der verlinkten Seiten ist stets der jeweilige
        Anbieter oder Betreiber der Seiten verantwortlich.</p>

      <h2>Urheberrecht</h2>
      <p>Die durch den Seitenbetreiber erstellten Inhalte und Werke auf diesen Seiten unterliegen dem deutschen Urheberrecht.
        Beiträge Dritter sind als solche gekennzeichnet.</p>
    </main>
  );
}
