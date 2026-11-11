import Link from "next/link";
import { LEGAL } from "@/lib/legal";

export const metadata = { title: "AGB · Planpause" };

export default function Agb() {
  const mail = <a href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a>;
  return (
    <main className="sheet legal">
      <h1>Allgemeine Geschäftsbedingungen</h1>
      <p className="hint">Stand: {LEGAL.updated}</p>

      <h2>§ 1 Geltungsbereich und Anbieter</h2>
      <p>Diese Bedingungen gelten für alle Verträge über die Nutzung von {LEGAL.product} zwischen {LEGAL.legalName}, {LEGAL.street},
        {" "}{LEGAL.zipCity} (im Folgenden „wir“) und unseren Kunden. Kunden können Verbraucher (§ 13 BGB) oder Unternehmer
        (§ 14 BGB) sein. Regelungen, die nur für eine dieser Gruppen gelten, sind als solche gekennzeichnet.</p>
      <p>Gegenüber Unternehmern gelten abweichende Bedingungen des Kunden nur, wenn wir ihnen ausdrücklich schriftlich zustimmen.</p>

      <h2>§ 2 Leistungen</h2>
      <p>{LEGAL.product} ist eine Webanwendung, die Fotos, Scans und PDF-Dateien von Bestandsgrundrissen auswertet. Sie liest
        Maßketten und Bauteile aus, prüft die Maße auf Widersprüche und erstellt daraus einen digitalen Grundriss mit Prüfbericht
        und DXF-Datei. Die Auswertung erfolgt automatisch und teilweise mit Hilfe künstlicher Intelligenz.</p>
      <p>Wir entwickeln {LEGAL.product} laufend weiter und dürfen Funktionen ändern, solange der Kern der Leistung erhalten bleibt
        und die Änderung für den Kunden zumutbar ist. Wir bemühen uns um eine hohe Verfügbarkeit. Unterbrechungen durch Wartung,
        Störungen oder Ursachen außerhalb unseres Einflussbereichs sind jedoch möglich.</p>

      <h2>§ 3 Konto und Vertragsschluss</h2>
      <p>Die Registrierung ist kostenlos. Mit ihr kommt ein unentgeltlicher Nutzungsvertrag über das Konto zustande. Die Angaben
        bei der Registrierung müssen wahr sein. Zugangsdaten sind geheim zu halten.</p>
      <p>Neue Konten können eine begrenzte Zahl kostenloser Grundrisse zum Ausprobieren erhalten. Ein Anspruch darauf besteht nicht.</p>
      <p>Kostenpflichtige Grundrisse und Pakete bestellt der Kunde per E-Mail oder über die Anwendung. Der Vertrag kommt zustande,
        wenn wir die Bestellung per E-Mail bestätigen oder das Kontingent freischalten. Die Vertragssprache ist Deutsch. Diese
        Bedingungen sind jederzeit unter <Link href="/agb">/agb</Link> abrufbar und können gespeichert oder gedruckt werden.</p>

      <h2>§ 4 Preise und Zahlung</h2>
      <p>Es gelten die zum Zeitpunkt der Bestellung auf unserer Website genannten Preise. Alle Preise sind Endpreise. Als
        Kleinunternehmer nach § 19 UStG weisen wir keine Umsatzsteuer aus.</p>
      <p>Wir stellen eine Rechnung per E-Mail. Sie ist innerhalb von 14 Tagen ohne Abzug per Überweisung zu zahlen.</p>
      <p>Ein Grundriss wird vom Kontingent abgezogen, wenn eine Auswertung gestartet wird. Bricht die Auswertung aus technischen
        Gründen ohne Ergebnis ab, wird der Grundriss wieder gutgeschrieben. Grundrisse aus Paketen können bis zum Ende des dritten
        Kalenderjahres nach dem Kauf genutzt werden.</p>

      <h2>§ 5 Hochgeladene Inhalte</h2>
      <p>Der Kunde lädt nur Pläne hoch, die er für den vorgesehenen Zweck verwenden darf. Grundrisse können urheberrechtlich
        geschützt sein, etwa durch das Urheberrecht des Architekten. Der Kunde stellt uns von Ansprüchen Dritter frei, die auf
        einer unberechtigten Nutzung der von ihm hochgeladenen Inhalte beruhen, soweit er dies zu vertreten hat.</p>
      <p>Der Kunde räumt uns das einfache Recht ein, die hochgeladenen Inhalte zu speichern und zu verarbeiten, soweit das zur
        Erbringung der Leistung und zur Behebung von Fehlern nötig ist. Eine Nutzung darüber hinaus findet nicht statt.</p>
      <p>Untersagt sind der Missbrauch der Anwendung, das Umgehen technischer Grenzen sowie automatisierte Massenzugriffe.</p>

      <h2>§ 6 Ergebnisse und Prüfpflicht</h2>
      <p>Die Ergebnisse werden automatisch erstellt. Sie können trotz sorgfältiger Auswertung Fehler enthalten, etwa falsch gelesene
        Maße, fehlende oder falsch zugeordnete Bauteile oder Abweichungen vom tatsächlichen Bestand. Ursache sind häufig Mängel der
        Vorlage selbst, zum Beispiel unleserliche, widersprüchliche oder veraltete Maßangaben. Die Ergebnisse ersetzen kein Aufmaß
        vor Ort.</p>
      <p>Der Kunde prüft Maße und Inhalte vor jeder Verwendung, insbesondere für Planung, Kalkulation, Bestellung oder Ausführung,
        in eigener Verantwortung. Ampel, Prüfpunkte und markierte Unstimmigkeiten sind Hilfen bei dieser Prüfung. Sie garantieren
        nicht, dass alle Fehler erkannt werden.</p>
      <p>Der Kunde darf die Ergebnisse uneingeschränkt nutzen. Rechte Dritter an der ursprünglichen Vorlage bleiben unberührt.</p>

      <h2>§ 7 Mängel</h2>
      <p><b>Unternehmer:</b> Ist ein Ergebnis aus von uns zu vertretenden Gründen unbrauchbar, etwa wegen eines technischen Fehlers,
        werten wir den Grundriss erneut aus oder schreiben ihn gut. Gelingt das nicht, erstatten wir den Preis für diesen
        Grundriss. Mängel sind innerhalb von 14 Tagen nach Erhalt des Ergebnisses per E-Mail mitzuteilen.</p>
      <p><b>Verbraucher:</b> Es gelten die gesetzlichen Mängelrechte, insbesondere §§ 327 ff. BGB für digitale Produkte.</p>

      <h2>§ 8 Haftung</h2>
      <p>Wir haften unbeschränkt bei Vorsatz und grober Fahrlässigkeit, bei der Verletzung von Leben, Körper oder Gesundheit, nach
        dem Produkthaftungsgesetz sowie im Rahmen einer übernommenen Garantie.</p>
      <p>Bei leichter Fahrlässigkeit haften wir nur für die Verletzung wesentlicher Vertragspflichten, also solcher Pflichten, deren
        Erfüllung die ordnungsgemäße Durchführung des Vertrags erst ermöglicht und auf deren Einhaltung der Kunde regelmäßig
        vertrauen darf. In diesem Fall ist die Haftung auf den vertragstypischen, vorhersehbaren Schaden begrenzt. Im Übrigen ist
        die Haftung für leichte Fahrlässigkeit ausgeschlossen.</p>
      <p>Schäden, die dadurch entstehen, dass Ergebnisse entgegen § 6 ohne Prüfung verwendet werden, fallen in den
        Verantwortungsbereich des Kunden (§ 254 BGB). Gegenüber Unternehmern ist die Haftung für Datenverlust auf den Aufwand
        begrenzt, der bei regelmäßiger Datensicherung durch den Kunden zur Wiederherstellung angefallen wäre. Der Kunde sollte
        heruntergeladene Ergebnisse selbst sichern.</p>
      <p>Diese Regelungen gelten auch zugunsten unserer Erfüllungsgehilfen.</p>

      <h2 id="widerruf">§ 9 Widerrufsrecht für Verbraucher</h2>
      <p>Verbrauchern steht bei kostenpflichtigen Bestellungen das folgende Widerrufsrecht zu.</p>

      <h3>Widerrufsbelehrung</h3>
      <p><b>Widerrufsrecht.</b> Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen.
        Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsabschlusses.</p>
      <p>Um Ihr Widerrufsrecht auszuüben, müssen Sie uns ({LEGAL.legalName}, {LEGAL.street}, {LEGAL.zipCity}, Telefon {LEGAL.phone},
        E-Mail {mail}) mittels einer eindeutigen Erklärung (z. B. ein mit der Post versandter Brief oder eine E-Mail) über Ihren
        Entschluss, diesen Vertrag zu widerrufen, informieren. Sie können dafür das unten stehende Muster-Widerrufsformular
        verwenden, das jedoch nicht vorgeschrieben ist. Zur Wahrung der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über
        die Ausübung des Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.</p>
      <p><b>Folgen des Widerrufs.</b> Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von Ihnen
        erhalten haben, unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die Mitteilung über
        Ihren Widerruf dieses Vertrags bei uns eingegangen ist. Für diese Rückzahlung verwenden wir dasselbe Zahlungsmittel, das
        Sie bei der ursprünglichen Transaktion eingesetzt haben, es sei denn, mit Ihnen wurde ausdrücklich etwas anderes
        vereinbart; in keinem Fall werden Ihnen wegen dieser Rückzahlung Entgelte berechnet.</p>
      <p>Haben Sie verlangt, dass die Dienstleistungen während der Widerrufsfrist beginnen sollen, so haben Sie uns einen
        angemessenen Betrag zu zahlen, der dem Anteil der bis zu dem Zeitpunkt, zu dem Sie uns von der Ausübung des
        Widerrufsrechts hinsichtlich dieses Vertrags unterrichten, bereits erbrachten Dienstleistungen im Vergleich zum
        Gesamtumfang der im Vertrag vorgesehenen Dienstleistungen entspricht.</p>
      <p><b>Erlöschen des Widerrufsrechts.</b> Das Widerrufsrecht erlischt, wenn wir mit der Auswertung begonnen haben, nachdem
        Sie ausdrücklich zugestimmt haben, dass wir vor Ablauf der Widerrufsfrist beginnen, und Sie bestätigt haben, dass Ihnen
        bekannt ist, dass Sie Ihr Widerrufsrecht damit verlieren. Bei Dienstleistungen erlischt es außerdem, wenn wir die
        Dienstleistung unter diesen Voraussetzungen vollständig erbracht haben.</p>

      <h3>Muster-Widerrufsformular</h3>
      <p>(Wenn Sie den Vertrag widerrufen wollen, dann füllen Sie bitte dieses Formular aus und senden Sie es zurück.)</p>
      <p>An {LEGAL.legalName}, {LEGAL.street}, {LEGAL.zipCity}, E-Mail {mail}:<br />
        Hiermit widerrufe(n) ich/wir (*) den von mir/uns (*) abgeschlossenen Vertrag über die Erbringung der folgenden
        Dienstleistung (*): ______<br />
        Bestellt am (*): ______<br />
        Name des/der Verbraucher(s): ______<br />
        Anschrift des/der Verbraucher(s): ______<br />
        Unterschrift des/der Verbraucher(s) (nur bei Mitteilung auf Papier): ______<br />
        Datum: ______<br />
        (*) Unzutreffendes streichen.</p>

      <h2>§ 10 Laufzeit und Kündigung</h2>
      <p>Der Nutzungsvertrag über das Konto läuft auf unbestimmte Zeit. Der Kunde kann ihn jederzeit per E-Mail an {mail} kündigen.
        Wir können ihn mit einer Frist von zwei Wochen kündigen. Das Recht zur Kündigung aus wichtigem Grund bleibt unberührt.</p>
      <p>Kündigen wir ordentlich, erstatten wir bezahlte, noch nicht genutzte Grundrisse aus Paketen anteilig. Vor dem Ende des
        Vertrags sollte der Kunde seine Ergebnisse herunterladen. Danach löschen wir die Daten nach Maßgabe der{" "}
        <Link href="/datenschutz">Datenschutzerklärung</Link>.</p>

      <h2>§ 11 Änderungen dieser Bedingungen</h2>
      <p>Änderungen dieser Bedingungen teilen wir registrierten Kunden per E-Mail mit. Sie gelten für Bestellungen, die nach der
        Mitteilung aufgegeben werden. Für bereits bezahlte Leistungen gelten die Bedingungen zum Zeitpunkt der Bestellung.</p>

      <h2>§ 12 Schlussbestimmungen</h2>
      <p>Es gilt das Recht der Bundesrepublik Deutschland unter Ausschluss des UN-Kaufrechts. Bei Verbrauchern gilt diese Rechtswahl
        nur, soweit dadurch nicht der Schutz durch zwingende Vorschriften des Staates entzogen wird, in dem sie ihren gewöhnlichen
        Aufenthalt haben.</p>
      <p>Ist der Kunde Kaufmann, juristische Person des öffentlichen Rechts oder öffentlich-rechtliches Sondervermögen, ist
        Gerichtsstand für alle Streitigkeiten aus diesem Vertrag unser Sitz.</p>
      <p>Hinweise zur Streitbeilegung stehen im <Link href="/impressum">Impressum</Link>. Sollte eine Bestimmung dieser Bedingungen
        unwirksam sein, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt.</p>
    </main>
  );
}
