// VORLAGE – alle Angaben in [eckigen Klammern] ersetzen und rechtlich prüfen lassen.
export default function Impressum() {
  return (
    <main className="sheet" style={{ padding: 24, maxWidth: 720 }}>
      <h1>Impressum</h1>
      <p>Angaben gemäß § 5 DDG</p>
      <p>[Name / Firma]<br />[Straße Hausnummer]<br />[PLZ Ort]</p>
      <p>Vertreten durch: [Name]</p>
      <p>Kontakt: [Telefon] · [E-Mail]</p>
      <p>[Registergericht, Registernummer, USt-IdNr., falls vorhanden]</p>
      <p>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV: [Name, Anschrift]</p>
    </main>
  );
}
