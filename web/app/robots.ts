import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

// Nur die öffentlichen Seiten gehören in die Suche, die App-Seiten sind ohnehin nur angemeldet nutzbar
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/projekte", "/projekt", "/grundriss", "/geschoss", "/login"] },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
