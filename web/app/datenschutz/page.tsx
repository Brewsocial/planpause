// VORLAGE – Gliederung für die Testphase. Vor dem Teilen ausfüllen und rechtlich prüfen lassen.
export default function Datenschutz() {
  return (
    <main className="sheet" style={{ padding: 24, maxWidth: 720, lineHeight: 1.55 }}>
      <h1>Datenschutzerklärung</h1>
      <h3>Verantwortlicher</h3>
      <p>[Name / Firma, Anschrift, E-Mail]</p>
      <h3>Welche Daten wir verarbeiten</h3>
      <p>
        Konto: E-Mail-Adresse und Passwort (verschlüsselt gespeichert). Projekte: hochgeladene Fotos und Scans von
        Grundrissen, eingegebene Notizen und Messwerte sowie die daraus berechneten Pläne. Grundrisse können
        Adressen oder Namen enthalten.
      </p>
      <h3>Zweck und Rechtsgrundlage</h3>
      <p>Bereitstellung der Plattform und Digitalisierung der Pläne (Art. 6 Abs. 1 lit. b DSGVO). [ergänzen]</p>
      <h3>Dienstleister (Auftragsverarbeiter)</h3>
      <ul>
        <li>Supabase Inc. – Anmeldung, Datenbank und Dateispeicher, Serverstandort [Region, z. B. Frankfurt].</li>
        <li>Anthropic PBC – KI-Auswertung der hochgeladenen Pläne. [Angaben zu Drittlandübermittlung und Speicherdauer ergänzen]</li>
        <li>[Hoster der Web-App und der API, Standort]</li>
      </ul>
      <h3>Speicherdauer</h3>
      <p>Projekte bleiben gespeichert, bis du sie löschst oder dein Zugang beendet wird. [ergänzen]</p>
      <h3>Deine Rechte</h3>
      <p>Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit, Widerspruch sowie Beschwerde bei einer Aufsichtsbehörde.</p>
    </main>
  );
}
