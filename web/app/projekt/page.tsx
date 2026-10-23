import { Suspense } from "react";
import FolderPage from "./FolderPage";

// Projekt (Ordner mit Grundrissen). Statischer Export: ID als Abfrageparameter (/projekt?id=…)
export default function Page() {
  return <Suspense fallback={<p className="muted">Lade Projekt …</p>}><FolderPage /></Suspense>;
}
