export type Axis = "x" | "y";
export type Rect = [number, number, number, number];

export interface MeasureHint { axis: Axis; a: string; b: string; expected: number | null; text: string }
export interface Issue {
  id: string; severity: "kritisch" | "pruefen" | "info"; category: string; title: string; detail: string;
  action: string; at: [number, number] | null; source: string; measure: MeasureHint[];
}
export interface Line { id: string; pos: number; status: "mass" | "flaeche" | "zeichnung"; sigma: number; label: string }
export interface Chain { id: string; axis: Axis; label: string; values: number[]; positions: number[]; total: number | null; sum: number; suspect: number[]; uncertain: number[] }
export interface Geometry {
  bbox: Rect;
  walls: { rect: Rect; kind: "aussen" | "innen" | "brand"; estimated: boolean }[];
  openings: { type: "window" | "door" | "gate" | "passage"; rect: Rect; estimated: boolean; width_stated: number | null;
    swing: { hinge: [number, number]; r: number; a0: number; a1: number } | null }[];
  features: { type: string; rect: Rect; estimated: boolean; treads: number | null; note: string }[];
  rooms: { name: string; area_stated: number | null; area_geom: number | null; poly: [number, number][]; label: [number, number] | null; estimated: boolean }[];
  zones: { type: string; poly: [number, number][] }[];
  chains: Chain[];
  lines: { x: Line[]; y: Line[] };
}
export interface Stats {
  lines_total: number; lines_measured: number; lines_from_area: number; lines_from_drawing: number;
  chains_total: number; chains_suspect: number; conflicts: number; rooms_checked: number; rooms_ok: number;
}
export interface Quality { level: "gut" | "eingeschraenkt" | "nicht_auswertbar"; reasons: string[]; tips: string[] }
export interface Result {
  geometry: Geometry; issues: Issue[]; stats: Stats; quality?: Quality;
  image_transform: { x: { scale: number; offset: number }; y: { scale: number; offset: number } } | null;
}
export interface Meta { id: string; name: string; status: string; created: number; updated: number; error?: string | null; demo?: boolean; steps?: string[]; quality?: Quality["level"]; warnings?: string[]; cost_usd?: number; last_cost_usd?: number; analyses?: number[];
  kind?: "folder"; folder_id?: string | null; floor?: string; part?: string }
export interface Placement { dx: number; dy: number; rot: 0 | 90 | 180 | 270 }
/** Projekt = Ordner mit mehreren Grundrissen (z. B. ein Haus) */
export interface Folder extends Meta { plans?: Meta[]; assembly?: Record<string, Record<string, Placement>> }
export interface Measurement { id: string; axis: Axis; a: string; b: string; value: number; note: string }
export interface Project { meta: Meta; plan: { title?: string; measurements?: Measurement[]; questions?: { id: string; question: string; why: string; type: string; options: string[]; unit: string; topic: string }[] }; result: Result | Record<string, never>; answers: Record<string, string> }
