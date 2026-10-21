import { LEGAL } from "@/lib/legal";

export const metadata = { title: "Datenschutz · Planpause" };

/** Sichtbare Markierung für Punkte, die vor der Veröffentlichung geprüft werden müssen. */
const Check = ({ children }: { children: React.ReactNode }) => <mark className="check-note">[prüfen: {children}]</mark>;

export default function Datenschutz() {
  const mail = <a href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a>;
  return (
    <main className="sheet legal">
      <h1>Datenschutzerklärung</h1>
      <p className="hint">Stand: {LEGAL.updated}</p>

      <h2>1. Verantwortlicher (Art. 13 DSGVO)</h2>
      <p>{LEGAL.name}<br />{LEGAL.street}<br />{LEGAL.zipCity}<br />{LEGAL.country}<br />E-Mail: {mail}</p>
      <p>Ein Datenschutzbeauftragter ist nicht bestellt, da die gesetzlichen Voraussetzungen (Art. 37 DSGVO, § 38 BDSG) nicht vorliegen.</p>

      <h2>2. Worum es geht</h2>
      <p>{LEGAL.product} digitalisiert Bestandsgrundrisse: Nutzer laden Fotos oder Scans von Grundrissen hoch, die Anwendung liest
        Maßketten und Bauteile aus, prüft die Maße auf Widersprüche und erstellt daraus einen digitalen Plan (z. B. als DXF-Datei).
        {" "}{LEGAL.product} befindet sich in der Testphase und ist nur für eingeladene Nutzer zugänglich.</p>

      <h2>3. Erhobene Daten und Zwecke</h2>

      <h3>a) Beim Aufruf der Anwendung</h3>
      <p>Beim Aufruf werden technisch bedingt folgende Daten verarbeitet: IP-Adresse, Datum und Uhrzeit des Zugriffs, aufgerufene
        Adresse, User-Agent (Browser, Betriebssystem). Die Daten laufen über das Netzwerk von Cloudflare (siehe Punkt 4) und werden
        vom Anwendungsserver kurzzeitig in Protokolldateien erfasst.</p>
      <p>Zweck: Bereitstellung der Anwendung, technische Sicherheit, Fehlerbehebung<br />
        Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse)<br />
        Speicherdauer: <Check>Aufbewahrungsdauer der Server-Protokolle festlegen, z. B. 7 Tage</Check></p>

      <h3>b) Benutzerkonto</h3>
      <p>Für die Nutzung ist ein Konto erforderlich, das wir auf Einladung anlegen. Verarbeitet werden: E-Mail-Adresse, Passwort
        (nur verschlüsselt gespeichert), Zeitpunkte von Anmeldungen sowie die Zuordnung zu einem Betrieb.</p>
      <p>Zweck: Anmeldung und Trennung der Daten verschiedener Betriebe<br />
        Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung bzw. Durchführung der Testphase)</p>

      <h3>c) Hochgeladene Pläne und Projektdaten</h3>
      <ul>
        <li>Fotos und Scans von Grundrissen, daraus aufbereitete Bilder</li>
        <li>Projektname und Hinweise zum Plan</li>
        <li>vor Ort gemessene Werte und Antworten auf Rückfragen</li>
        <li>daraus berechnete Pläne, Prüfberichte und Exportdateien</li>
      </ul>
      <p>Grundrisse können personenbezogene Daten enthalten, etwa Anschriften, Namen von Eigentümern, Planverfassern oder
        Unterschriften. Bitte laden Sie nur Pläne hoch, zu deren Verarbeitung Sie berechtigt sind, und decken Sie nicht benötigte
        Angaben nach Möglichkeit ab.</p>
      <p>Zweck: Digitalisierung und Prüfung der Pläne<br />
        Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO; soweit Daten Dritter enthalten sind, Art. 6 Abs. 1 lit. f DSGVO
        <Check>Rechtsgrundlage für Daten Dritter in Plänen und Rolle als Auftragsverarbeiter für Betriebe (siehe Punkt 5)</Check></p>

      <h3>d) Auswertung mit künstlicher Intelligenz</h3>
      <p>Zum Auslesen der Pläne wird das aufbereitete Bild zusammen mit den Hinweisen zum Plan an die Programmierschnittstelle
        des KI-Anbieters Anthropic übermittelt (siehe Punkt 4). Die KI beschreibt den Plan (Maßzahlen, Wände, Räume); die eigentliche
        Berechnung der Maße erfolgt anschließend durch unsere Software. Es findet keine automatisierte Entscheidung im Sinne von
        Art. 22 DSGVO statt.</p>
      <p>Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO</p>

      <h3>e) Speicherung im Browser</h3>
      <p>Damit Sie angemeldet bleiben, speichert die Anwendung ein Anmelde-Token im lokalen Speicher Ihres Browsers. Das ist für
        den von Ihnen gewünschten Dienst technisch erforderlich (§ 25 Abs. 2 Nr. 2 TDDDG). Es werden keine Cookies zu Werbe- oder
        Analysezwecken gesetzt, keine Analyse- oder Tracking-Dienste eingesetzt und keine Schriften oder Inhalte von Drittanbietern
        nachgeladen.</p>

      <h2>4. Empfänger der Daten / Dienstleister</h2>

      <h3>a) Supabase (Anmeldung, Datenbank, Dateispeicher)</h3>
      <p>Anbieter: Supabase Inc., 970 Trestle Glen Rd, Oakland, CA 94610, USA<br />
        Verarbeitungstätigkeit: Benutzerkonten, Projektdaten, hochgeladene Bilder und Ergebnisse<br />
        Speicherort: <Check>Region des Supabase-Projekts, z. B. EU (Frankfurt)</Check><br />
        Auftragsverarbeitung: Vertrag nach Art. 28 DSGVO <Check>AV-Vertrag mit Supabase abgeschlossen</Check><br />
        Drittlandtransfer: Soweit eine Übermittlung in die USA stattfindet (z. B. Support-Zugriffe), erfolgt sie auf Grundlage der
        EU-Standardvertragsklauseln gemäß Art. 46 Abs. 2 lit. c DSGVO.<br />
        Datenschutzerklärung: <a href="https://supabase.com/privacy">supabase.com/privacy</a></p>

      <h3>b) Anthropic (KI-Auswertung)</h3>
      <p>Anbieter: Anthropic PBC, 548 Market Street, PMB 90375, San Francisco, CA 94104, USA <Check>Anschrift aus dem AV-Vertrag übernehmen</Check><br />
        Verarbeitungstätigkeit: Auslesen der hochgeladenen Pläne (siehe Punkt 3 d)<br />
        Auftragsverarbeitung: Vertrag nach Art. 28 DSGVO <Check>Data Processing Addendum von Anthropic abgeschlossen</Check><br />
        Nutzung und Speicherdauer beim Anbieter: <Check>laut aktuellen kommerziellen Bedingungen und AV-Vertrag von Anthropic eintragen,
          insbesondere ob Eingaben zum Training verwendet werden und wie lange sie gespeichert bleiben</Check><br />
        Drittlandtransfer: Übermittlung in die USA auf Grundlage der EU-Standardvertragsklauseln gemäß Art. 46 Abs. 2 lit. c DSGVO
        <Check>ob Anthropic nach dem EU-US Data Privacy Framework zertifiziert ist</Check><br />
        Datenschutzerklärung: <a href="https://www.anthropic.com/legal/privacy">anthropic.com/legal/privacy</a></p>

      <h3>c) Cloudflare (Auslieferung und Netzwerk)</h3>
      <p>Anbieter: Cloudflare, Inc., 101 Townsend St., San Francisco, CA 94107, USA<br />
        Verarbeitungstätigkeit: Auslieferung der Anwendung, verschlüsselte Weiterleitung der Anfragen an den Anwendungsserver,
        Schutz vor Angriffen; dabei werden insbesondere IP-Adressen verarbeitet<br />
        Auftragsverarbeitung: Vertrag nach Art. 28 DSGVO <Check>AV-Vertrag mit Cloudflare abgeschlossen</Check><br />
        Drittlandtransfer: <Check>Zertifizierung nach dem EU-US Data Privacy Framework bzw. Standardvertragsklauseln</Check><br />
        Datenschutzerklärung: <a href="https://www.cloudflare.com/privacypolicy/">cloudflare.com/privacypolicy</a></p>

      <h3>d) Anwendungsserver</h3>
      <p>Während der Testphase wird der Anwendungsserver (Bildaufbereitung, Berechnung, Export) vom Verantwortlichen selbst in
        Deutschland betrieben. <Check>bei Umzug zu einem Hosting-Anbieter hier ergänzen</Check></p>

      <h2>5. Hinweis für Betriebe: Auftragsverarbeitung</h2>
      <p>Laden Betriebe Pläne ihrer Kunden hoch, verarbeiten wir die darin enthaltenen personenbezogenen Daten in ihrem Auftrag.
        Einen Vertrag zur Auftragsverarbeitung nach Art. 28 DSGVO stellen wir auf Anfrage bereit. <Check>Rollenverteilung und
        AV-Vertrag mit den testenden Betrieben</Check></p>

      <h2>6. Speicherdauer</h2>
      <p>Projekte bleiben gespeichert, bis Sie sie in der Anwendung löschen („Projekt löschen“) oder Ihr Zugang beendet wird. Beim
        Löschen eines Projekts werden die hochgeladenen Bilder, Ergebnisse und Protokolle entfernt. Nach Ende Ihres Zugangs löschen
        wir Konto und Projektdaten innerhalb von 30 Tagen. <Check>Löschfristen, Backups bei Supabase und gesetzliche
        Aufbewahrungspflichten</Check></p>

      <h2>7. Ihre Rechte (Art. 15–22 DSGVO)</h2>
      <p>Sie haben jederzeit das Recht auf:</p>
      <ul>
        <li>Auskunft über Ihre gespeicherten Daten (Art. 15 DSGVO)</li>
        <li>Berichtigung unrichtiger Daten (Art. 16 DSGVO)</li>
        <li>Löschung (Art. 17 DSGVO)</li>
        <li>Einschränkung der Verarbeitung (Art. 18 DSGVO)</li>
        <li>Datenübertragbarkeit (Art. 20 DSGVO)</li>
        <li>Widerspruch gegen Verarbeitungen auf Grundlage von Art. 6 Abs. 1 lit. f DSGVO (Art. 21 DSGVO)</li>
        <li>Widerruf erteilter Einwilligungen mit Wirkung für die Zukunft (Art. 7 Abs. 3 DSGVO)</li>
      </ul>
      <p>Zur Ausübung Ihrer Rechte genügt eine E-Mail an {mail}.</p>

      <h2>8. Beschwerderecht</h2>
      <p>Sie haben das Recht, sich bei einer Datenschutzaufsichtsbehörde über die Verarbeitung Ihrer personenbezogenen Daten zu
        beschweren. Für den Verantwortlichen zuständig ist:</p>
      <p>Der Hessische Beauftragte für Datenschutz und Informationsfreiheit (HBDI)<br />Postfach 3163<br />65021 Wiesbaden<br />
        <a href="https://datenschutz.hessen.de">datenschutz.hessen.de</a></p>
      <p>Sie können sich auch an die Aufsichtsbehörde Ihres Wohnsitzes oder Ihres Unternehmenssitzes wenden.</p>

      <h2>9. Änderungen dieser Datenschutzerklärung</h2>
      <p>Wir passen diese Datenschutzerklärung an, wenn sich die Anwendung, die eingesetzten Dienstleister oder die Rechtslage
        ändern. Die jeweils aktuelle Fassung ist in der Anwendung abrufbar.</p>
    </main>
  );
}
