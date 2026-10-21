import { Suspense } from "react";
import ProjectPage from "./ProjectPage";

// Statischer Export: Projekt-ID als Abfrageparameter (/projekt?id=…) statt dynamischem Pfad
export default function Page() {
  return <Suspense fallback={<p className="muted">Lade Projekt …</p>}><ProjectPage /></Suspense>;
}
