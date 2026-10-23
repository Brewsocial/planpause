"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Vorschaubild des aufbereiteten Plans (über die API, weil Bilder nur angemeldet abrufbar sind). */
export default function Thumb({ id }: { id: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let u = "";
    api.blob(`/projects/${id}/image`).then((b) => { u = URL.createObjectURL(b); setUrl(u); }).catch(() => setUrl(""));
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [id]);
  return url ? <img src={url} alt="" loading="lazy" /> : <span className="hint">Kein Bild</span>;
}
