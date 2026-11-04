"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const ModelView = dynamic(() => import("@/components/ModelView"), { ssr: false, loading: () => <p className="muted">3D-Ansicht wird geladen …</p> });

/** Beispielmodell der Startseite. three.js und das Modell laden erst, wenn der Abschnitt in die Nähe des Bildschirms kommt. */
export default function LandingModel() {
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setNear(true); io.disconnect(); } }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className="lp-model">
      {near ? <ModelView src="/demo-p8.json" compact /> : <div className="model3d-view" aria-hidden="true" />}
    </div>
  );
}
