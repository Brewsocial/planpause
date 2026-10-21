import type { Metadata } from "next";
import Link from "next/link";
import { Account, AuthGate } from "@/components/AuthGate";
import "./globals.css";

export const metadata: Metadata = { title: "Planpause", description: "Bestandsgrundrisse digitalisieren und prüfen" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" />
      </head>
      <body>
        <div className="wrap">
          <header className="top">
            <Link href="/" className="brand"><b>Planpause</b><span>Bestandsplan → CAD</span></Link>
            <div className="spacer" />
            <Account />
          </header>
          <AuthGate>{children}</AuthGate>
          <footer className="hint" style={{ display: "flex", gap: 16, padding: "32px 0 20px" }}>
            <Link href="/impressum">Impressum</Link>
            <Link href="/datenschutz">Datenschutz</Link>
          </footer>
        </div>
      </body>
    </html>
  );
}
