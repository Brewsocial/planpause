import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import { Account, AuthGate } from "@/components/AuthGate";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

// Inter wie auf der KiCO-Website: liegt im Projekt und wird selbst ausgeliefert, keine Verbindung zu Google.
// Lizenz: app/fonts/Inter-LICENSE.txt
const inter = localFont({ src: "./fonts/inter-latin-wght-normal.woff2", weight: "100 900", variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "Planpause", template: "%s · Planpause" },
  description: "Bestandsgrundrisse digitalisieren: Foto, Scan oder PDF hochladen und eine maßhaltige DXF aus den Maßketten erhalten.",
};
// Immer hell, auch wenn das Handy im Dunkelmodus ist (wie die KiCO-Website)
export const viewport: Viewport = { themeColor: "#f5f5f7", colorScheme: "light" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={inter.variable}>
      <body>
        <div className="wrap">
          <header className="top">
            <div className="top-in">
              <Link href="/" className="brand"><b>Planpause</b><span>Bestandsplan → CAD</span></Link>
              <div className="spacer" />
              <Account />
            </div>
          </header>
          <AuthGate>{children}</AuthGate>
          <footer className="foot">
            <span>Planpause · ein Produkt von KiCO</span>
            <Link href="/impressum">Impressum</Link>
            <Link href="/datenschutz">Datenschutz</Link>
          </footer>
        </div>
      </body>
    </html>
  );
}
