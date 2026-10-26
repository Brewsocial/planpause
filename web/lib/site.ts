/** Öffentliche Adresse der Website (für Suchmaschinen: Canonical, Sitemap, Vorschaukarten). Bei eigener Domain hier oder per Umgebungsvariable ändern. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://planpause.info-brewsocial.workers.dev").replace(/\/$/, "");
