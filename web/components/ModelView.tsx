"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api, type ModelMesh } from "@/lib/api";

const LABEL: Record<string, string> = {
  IfcWall: "Wand", IfcWindow: "Fenster", IfcDoor: "Tür", IfcSpace: "Raum", IfcStair: "Treppe",
  IfcColumn: "Stütze", IfcChimney: "Schornstein", IfcBuildingElementProxy: "Bauteil",
};
const COLOR: Record<string, number> = {
  IfcWall: 0xdedee3, IfcWindow: 0x7db8f0, IfcDoor: 0xb07a4a, IfcSpace: 0x0071e3, IfcStair: 0x6e6e73,
  IfcColumn: 0x9a9aa0, IfcChimney: 0x8a6f68, IfcBuildingElementProxy: 0xb0b0b6,
};
const ESTIMATED = 0xf0b45a;

/**
 * 3D-Ansicht des IFC-Bestandsmodells. Die API rechnet das Modell in Dreiecke um (dasselbe Modell wie beim
 * IFC-Download), hier wird es nur angezeigt. Drehen mit einem Finger, zoomen mit zwei, verschieben mit rechts/zwei Fingern.
 */
export default function ModelView({ path, height }: { path: string; height: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [meshes, setMeshes] = useState<ModelMesh[] | null>(null);
  const [err, setErr] = useState("");
  const [rooms, setRooms] = useState(false);
  const [estimated, setEstimated] = useState(false);
  const [picked, setPicked] = useState("");

  useEffect(() => {  // Raumhöhe ändert das Modell: kurz warten, dann neu laden
    setErr("");
    const t = setTimeout(() => api.model(path, height).then(setMeshes).catch((e) => setErr(e.message)), 350);
    return () => clearTimeout(t);
  }, [path, height]);

  useEffect(() => {
    const el = box.current;
    if (!el || !meshes) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0xf5f5f7);
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0xb8b8c0, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-0.6, 1, 0.8);
    scene.add(sun);

    const model = new THREE.Group();
    model.rotation.x = -Math.PI / 2;  // IFC: z nach oben, three.js: y nach oben
    const pickable: THREE.Mesh[] = [];
    for (const m of meshes) {
      if (m.type === "IfcSpace" && !rooms) continue;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(m.verts, 3));
      geo.setIndex(m.faces);
      geo.computeVertexNormals();
      const space = m.type === "IfcSpace";
      const color = estimated && m.estimated && !space ? ESTIMATED : COLOR[m.type] ?? 0xb0b0b6;
      const mat = new THREE.MeshStandardMaterial({
        color, roughness: 0.9, side: THREE.DoubleSide,
        transparent: space || m.type === "IfcWindow", opacity: space ? 0.14 : m.type === "IfcWindow" ? 0.55 : 1,
        depthWrite: !space, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.userData = m;
      model.add(mesh);
      if (!space || rooms) pickable.push(mesh);
      if (!space) {
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: 0x55555a }));
        model.add(edges);
      }
    }
    scene.add(model);

    // Kamera auf das Modell ausrichten: schräg von vorne oben
    const bb = new THREE.Box3().setFromObject(model);
    const center = bb.getCenter(new THREE.Vector3());
    const size = bb.getSize(new THREE.Vector3()).length() || 10;
    // Abstand so, dass die Hüllkugel des Modells in den engeren Öffnungswinkel passt (Handy hochkant: der waagerechte)
    const aspect = el.clientWidth / Math.max(1, el.clientHeight);
    const vfov = THREE.MathUtils.degToRad(40);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
    const dist = (size / 2) / Math.sin(Math.min(vfov, hfov) / 2) * 0.82;  // Kugel ist großzügig: etwas näher heran
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
      const r = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
      const hit = ray.intersectObjects(pickable)[0];
      const m = hit?.object.userData as ModelMesh | undefined;
      setPicked(m ? `${LABEL[m.type] ?? m.type}${m.name && m.name !== LABEL[m.type] ? `: ${m.name}` : ""}${m.estimated ? " (Lage geschätzt)" : ""}` : "");
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
      model.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) { o.geometry.dispose(); (o.material as THREE.Material).dispose(); }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [meshes, rooms, estimated]);

  return (
    <div className="model3d">
      <div className="model3d-view" ref={box} style={{ touchAction: "none" }}>
        {!meshes && !err && <p className="muted model3d-msg">Modell wird berechnet …</p>}
        {picked && <span className="model3d-pick">{picked}</span>}
      </div>
      {err && <p className="err" style={{ margin: 0 }}>{err}</p>}
      <div className="model3d-bar">
        <label className="check"><input type="checkbox" checked={rooms} onChange={(e) => setRooms(e.target.checked)} /> Räume zeigen</label>
        <label className="check"><input type="checkbox" checked={estimated} onChange={(e) => setEstimated(e.target.checked)} /> Geschätzte Teile <i className="model3d-dot" /></label>
        <span className="hint">Ziehen dreht, zwei Finger oder Mausrad zoomen. Antippen zeigt das Bauteil.</span>
      </div>
    </div>
  );
}
