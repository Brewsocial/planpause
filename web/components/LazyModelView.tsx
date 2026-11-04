"use client";

import dynamic from "next/dynamic";

/**
 * 3D-Ansicht, erst bei Bedarf geladen (three.js ist groß). Wurde die App seit dem Öffnen der Seite neu ausgeliefert,
 * gibt es die alte Datei der 3D-Ansicht nicht mehr: dann einmal die Seite neu laden statt mit einem Fehler abzubrechen.
 */
const ModelView = dynamic(() => import("@/components/ModelView").catch((e) => {
  const key = "planpause-reload-3d";
  let again = false;
  try { again = sessionStorage.getItem(key) === "1"; sessionStorage.setItem(key, "1"); } catch { /* ohne Speicher: nicht neu laden */ again = true; }
  if (!again) { window.location.reload(); return new Promise<never>(() => {}); }
  throw e;
}).then((m) => { try { sessionStorage.removeItem("planpause-reload-3d"); } catch { /* egal */ } return m; }),
{ ssr: false, loading: () => <p className="muted">3D-Ansicht wird geladen …</p> });

export default ModelView;
