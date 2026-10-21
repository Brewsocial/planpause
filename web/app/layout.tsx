import type { Metadata } from "next";
import { Barlow_Condensed, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { Account, AuthGate } from "@/components/AuthGate";
import "./globals.css";

// Schriften werden beim Bauen heruntergeladen und mit der App ausgeliefert: keine Verbindung zu Google im Browser
const display = Barlow_Condensed({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-display" });
const body = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-body" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Planpause", description: "Bestandsgrundrisse digitalisieren und prüfen" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={`${display.variable} ${body.variable} ${mono.variable}`}>
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
