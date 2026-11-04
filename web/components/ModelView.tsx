"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api, type ModelMesh } from "@/lib/api";

const LABEL: Record<string, string> = {
  IfcWall: "Wand", IfcWindow: "Fenster", IfcDoor: "Tür", IfcSpace: "Raum", IfcStair: "Treppe", IfcSlab: "Decke",
  IfcColumn: "Stütze", IfcChimney: "Schornstein", IfcBuildingElementProxy: "Bauteil",
};
// Materialfarben wie in einem Architekturmodell: Putz, Beton, Glas, Holz, Kies, Ziegel
const PUTZ = 0xefeae2, INNEN = 0xf7f6f3, BETON = 0xb5b3ad, GLAS = 0x2f3d4b, HOLZ = 0x9a6b45, KIES = 0x7a7c79, ZIEGEL = 0x8c5640,
  SOCKEL = 0x8d8a84, LOGGIA = 0xb9774f;
const ESTIMATED = 0xf0b45a;

function look(m: ModelMesh): { color: number; rough: number; metal: number } {
  if (m.type === "IfcWindow") return { color: GLAS, rough: 0.25, metal: 0.35 };
  if (m.type === "IfcDoor") return m.name === "Fenstertür" ? { color: GLAS, rough: 0.25, metal: 0.35 } : { color: m.kind === "GATE" ? BETON : HOLZ, rough: 0.7, metal: 0 };
  if (m.type === "IfcSlab") return { color: m.kind === "ROOF" ? KIES : BETON, rough: 0.95, metal: 0 };
  if (m.type === "IfcChimney") return { color: ZIEGEL, rough: 0.9, metal: 0 };
  if (m.type === "IfcStair" || m.type === "IfcColumn") return { color: BETON, rough: 0.9, metal: 0 };
  if (m.type === "IfcWall") {
    const n = m.name;
    const color = n.startsWith("Loggia Rück") || n.startsWith("Loggia Seite") ? LOGGIA : n === "Attika" || n.includes("Brüstung") ? BETON
      : n.includes("Sockel") ? SOCKEL : m.kind === "innen" ? INNEN : PUTZ;
    return { color, rough: 0.92, metal: 0 };
  }
  return { color: 0xc9c7c1, rough: 0.9, metal: 0 };
}

const zmin = (m: ModelMesh) => { let z = Infinity; for (let i = 2; i < m.verts.length; i += 3) z = Math.min(z, m.verts[i]); return z; };

/**
 * 3D-Ansicht des IFC-Bestandsmodells. Die API rechnet das Modell in Dreiecke um (dasselbe Modell wie beim
 * IFC-Download), hier wird es nur angezeigt. Drehen mit einem Finger, zoomen mit zwei, verschieben mit rechts/zwei Fingern.
 * height: lichte Raumhöhe in m (nur bei Grundriss und Geschoss; das Gebäude hat eigene Geschosshöhen).
 * src: statt path eine öffentliche Datei mit fertigen Dreiecksnetzen (Beispielmodell der Startseite); compact blendet
 * die Schalter für Räume und geschätzte Teile aus.
 */
export default function ModelView({ path, height, src, compact }: { path?: string; height?: number; src?: string; compact?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [meshes, setMeshes] = useState<ModelMesh[] | null>(null);
  const [err, setErr] = useState("");
  const [rooms, setRooms] = useState(false);
  const [estimated, setEstimated] = useState(false);
  const [picked, setPicked] = useState("");
  const [upTo, setUpTo] = useState(-1);  // oberstes sichtbares Geschoss (Index), -1 = alle

  useEffect(() => {  // Raumhöhe ändert das Modell: kurz warten, dann neu laden
    setErr("");
    const load = src ? () => fetch(src).then((r) => r.json() as Promise<ModelMesh[]>) : () => api.model(path ?? "", height);
    const t = setTimeout(() => load().then(setMeshes).catch((e) => setErr(e.message)), src ? 0 : 350);
    return () => clearTimeout(t);
  }, [path, height, src]);

  // Geschosse von unten nach oben, für „Geschosse bis …“
  const storeys = useMemo(() => {
    if (!meshes) return [];
    const low = new Map<string, number>();
    for (const m of meshes) if (m.storey) low.set(m.storey, Math.min(low.get(m.storey) ?? Infinity, zmin(m)));
    return [...low.entries()].sort((a, b) => a[1] - b[1]).map(([s]) => s);
  }, [meshes]);

  useEffect(() => {
    const el = box.current;
    if (!el || !meshes) return;
    const sky = new THREE.Color(getComputedStyle(el).backgroundColor);
    const dark = sky.getHSL({ h: 0, s: 0, l: 0 }).l < 0.4;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = sky;
    scene.add(new THREE.HemisphereLight(0xf3f6ff, 0x8f8a7e, dark ? 1.3 : 1.6));

    const visible = new Set(upTo < 0 ? storeys : storeys.slice(0, upTo + 1));
    const model = new THREE.Group();
    model.rotation.x = -Math.PI / 2;  // IFC: z nach oben, three.js: y nach oben
    const pickable: THREE.Mesh[] = [];
    for (const m of meshes) {
      if (m.type === "IfcSpace" && !rooms) continue;
      if (m.storey && !visible.has(m.storey)) continue;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(m.verts, 3));
      geo.setIndex(m.faces);
      geo.computeVertexNormals();
      const space = m.type === "IfcSpace";
      const l = look(m);
      const mat = new THREE.MeshStandardMaterial({
        color: space ? 0x0071e3 : estimated && m.estimated ? ESTIMATED : l.color, roughness: l.rough, metalness: l.metal,
        side: THREE.DoubleSide, transparent: space, opacity: space ? 0.14 : 1,
        depthWrite: !space, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = !space;
      mesh.receiveShadow = !space;
      mesh.userData = m;
      model.add(mesh);
      if (!space || rooms) pickable.push(mesh);
      if (!space && m.type !== "IfcWindow") {
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25),
          new THREE.LineBasicMaterial({ color: 0x3a3c42, transparent: true, opacity: 0.18 }));
        model.add(edges);
      }
    }
    scene.add(model);

    // Kamera auf das Modell ausrichten: schräg von vorne oben
    const bb = new THREE.Box3().setFromObject(model);
    const center = bb.getCenter(new THREE.Vector3());
    const size = bb.getSize(new THREE.Vector3()).length() || 10;

    // Boden mit Schlagschatten, Horizont läuft im Dunst aus
    const ground = new THREE.Mesh(new THREE.CircleGeometry(size * 20, 64),
      new THREE.MeshStandardMaterial({ color: dark ? 0x3a3d3a : 0xd9dcd3, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = bb.min.y - 0.01;
    ground.receiveShadow = true;
    scene.add(ground);
    scene.fog = new THREE.Fog(sky, size * 3, size * 10);

    // Sonne aus Südost: Westseite im Schatten, Schatten fällt sichtbar neben das Gebäude
    const sun = new THREE.DirectionalLight(0xfff3e2, dark ? 2.0 : 2.4);
    sun.target.position.copy(center);
    sun.position.copy(center).add(new THREE.Vector3(1, 1.4, 0.9).normalize().multiplyScalar(size * 1.5));
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.03;
    const r = size * 0.75;
    Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: size * 0.1, far: size * 4 });
    scene.add(sun, sun.target);

    // Abstand so, dass die Hüllkugel des Modells in den engeren Öffnungswinkel passt (Handy hochkant: der waagerechte)
    const aspect = el.clientWidth / Math.max(1, el.clientHeight);
    const vfov = THREE.MathUtils.degToRad(40);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
    const dist = (size / 2) / Math.sin(Math.min(vfov, hfov) / 2) * 1.0;  // ganze Hüllkugel, damit auch hohe Gebäude samt Dach ins Bild passen
    const camera = new THREE.PerspectiveCamera(40, aspect, size / 200, size * 20);
    camera.position.copy(center).add(new THREE.Vector3(-0.45, 0.75, 0.85).normalize().multiplyScalar(dist));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.49;  // nicht unter den Boden
    controls.update();

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    // Antippen zeigt, welches Bauteil es ist (nur bei kurzem Tippen, nicht nach dem Drehen)
    const ray = new THREE.Raycaster();
    let down: [number, number] | null = null;
    const onDown = (e: PointerEvent) => { down = [e.clientX, e.clientY]; };
    const onUp = (e: PointerEvent) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
      const rc = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - rc.left) / rc.width) * 2 - 1, -((e.clientY - rc.top) / rc.height) * 2 + 1), camera);
      const hit = ray.intersectObjects(pickable)[0];
      const m = hit?.object.userData as ModelMesh | undefined;
      setPicked(m ? `${LABEL[m.type] ?? m.type}${m.name && m.name !== LABEL[m.type] ? `: ${m.name}` : ""}${storeys.length > 1 && m.storey ? ` · ${m.storey}` : ""}${m.estimated ? " (Lage geschätzt)" : ""}` : "");
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    let frame = 0;
    const loop = () => { frame = requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); };
    loop();
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) { o.geometry.dispose(); (o.material as THREE.Material).dispose(); }
      });
      sun.shadow.map?.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [meshes, rooms, estimated, upTo, storeys]);

  return (
    <div className="model3d">
      <div className="model3d-view" ref={box} style={{ touchAction: "none" }}>
        {!meshes && !err && <p className="muted model3d-msg">Modell wird berechnet …</p>}
        {picked && <span className="model3d-pick">{picked}</span>}
      </div>
      {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
      <div className="model3d-bar">
        {storeys.length > 1 && (
          <label className="check">Geschosse bis
            <select value={upTo} onChange={(e) => setUpTo(+e.target.value)}>
              <option value={-1}>alle</option>
              {storeys.map((s, i) => <option key={s} value={i}>{s}</option>)}
            </select>
          </label>)}
        {!compact && <>
          <label className="check"><input type="checkbox" checked={rooms} onChange={(e) => setRooms(e.target.checked)} /> Räume zeigen</label>
          <label className="check"><input type="checkbox" checked={estimated} onChange={(e) => setEstimated(e.target.checked)} /> Geschätzte Teile <i className="model3d-dot" /></label>
        </>}
        <span className="hint">Ziehen dreht, zwei Finger oder Mausrad zoomen. Antippen zeigt das Bauteil.</span>
      </div>
    </div>
  );
}
