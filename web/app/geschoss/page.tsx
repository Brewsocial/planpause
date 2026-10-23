import { Suspense } from "react";
import FloorPage from "./FloorPage";

// Geschoss aus mehreren Zeichnungen zusammensetzen (/geschoss?projekt=…&g=EG)
export default function Page() {
  return <Suspense fallback={<p className="muted">Lade Geschoss …</p>}><FloorPage /></Suspense>;
}
