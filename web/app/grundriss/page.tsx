import { Suspense } from "react";
import PlanPage from "./PlanPage";

// Statischer Export: Projekt-ID als Abfrageparameter (/grundriss?id=…) statt dynamischem Pfad
export default function Page() {
  return <Suspense fallback={<p className="muted">Lade Projekt …</p>}><PlanPage /></Suspense>;
}
