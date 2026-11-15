"use client";

import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { animate, useMotionValue, type MotionValue } from "motion/react";
import { Suspense, useEffect, useMemo, useRef, type RefObject } from "react";
import {
  Mesh,
  CanvasTexture,
  Vector3,
  type Object3D,
  OrthographicCamera,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const WIDTH = 900;
const HEIGHT = 600;
const cameraPosition = [10, 11.2, 14.8] as const;
const personStart = [-1.9, 1.27] as const;
const personEnd = [-0.7, 0.69] as const;
const liftStart = [2.35, 0.68] as const;
const liftEnd = [0.95, 0.32] as const;
const zone = [
  [-2.6, -0.75],
  [2.55, -0.75],
  [2.55, 1.65],
  [-2.6, 1.65],
] as const;
const clamp = (v: number) => Math.min(1, Math.max(0, v));

function makeShadow() {
  const image = document.createElement("canvas");
  image.width = image.height = 64;
  const brush = image.getContext("2d");
  if (brush) {
    const gradient = brush.createRadialGradient(32, 32, 5, 32, 32, 32);
    gradient.addColorStop(0, "rgba(16, 31, 53, .55)");
    gradient.addColorStop(0.48, "rgba(16, 31, 53, .30)");
    gradient.addColorStop(1, "rgba(16, 31, 53, 0)");
    brush.fillStyle = gradient;
    brush.fillRect(0, 0, 64, 64);
  }
  return new CanvasTexture(image);
}

type Marks = {
  worker: SVGSVGElement;
  lift: SVGSVGElement;
  trails: SVGGElement;
  workerTrack: SVGLineElement;
  liftTrack: SVGLineElement;
  cameraSignal: SVGGElement;
  cameraLine: SVGLineElement;
  spatial: SVGGElement;
  zone: SVGPolygonElement;
  distance: SVGLineElement;
  event: SVGGElement;
  eventPoint: SVGCircleElement;
};

function opacity(node: SVGElement, value: number) {
  node.style.opacity = String(clamp(value));
}

function line(node: SVGLineElement, start: Vector3, end: Vector3) {
  node.setAttribute("x1", String(start.x));
  node.setAttribute("y1", String(start.y));
  node.setAttribute("x2", String(end.x));
  node.setAttribute("y2", String(end.y));
}

function drawBox(
  svg: SVGSVGElement,
  object: Object3D,
  project: (point: Vector3) => Vector3,
) {
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  object.updateWorldMatrix(true, true);
  const vertex = new Vector3();
  object.traverse((node) => {
    if (!(node instanceof Mesh)) return;
    const { geometry, matrixWorld } = node;
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    if (!box) return;
    for (const x of [box.min.x, box.max.x])
      for (const y of [box.min.y, box.max.y])
        for (const z of [box.min.z, box.max.z]) {
          const point = project(vertex.set(x, y, z).applyMatrix4(matrixWorld));
          minX = Math.min(minX, point.x);
          maxX = Math.max(maxX, point.x);
          minY = Math.min(minY, point.y);
          maxY = Math.max(maxY, point.y);
        }
  });
  svg.setAttribute("x", String(minX - 3));
  svg.setAttribute("y", String(minY - 29));
  svg.setAttribute("width", String(maxX - minX + 6));
  svg.setAttribute("height", String(maxY - minY + 32));
}

function Warehouse({
  clock,
  overlay,
  onReady,
  onCapture,
}: {
  clock: MotionValue<number>;
  overlay: RefObject<SVGSVGElement | null>;
  onReady: () => void;
  onCapture: (image: string) => void;
}) {
  const { scene } = useLoader(
    GLTFLoader,
    "/experience/warehouse.glb",
    (loader) => loader.setMeshoptDecoder(MeshoptDecoder),
  );
  const { camera, invalidate, gl, scene: renderScene } = useThree();
  const captured = useRef(false);
  const shadow = useMemo(() => makeShadow(), []);
  const workerShadow = useRef<Mesh>(null);
  const liftShadow = useRef<Mesh>(null);
  const worker = scene.getObjectByName("Worker");
  const lift = scene.getObjectByName("Forklift");
  const legs = ["LegL", "LegR", "ArmL", "ArmR"].map((name) =>
    worker?.getObjectByName(name),
  );
  const wheels = ["Wheel0L", "Wheel0R", "Wheel1L", "Wheel1R"].map((name) =>
    lift?.getObjectByName(name),
  );

  useEffect(() => {
    invalidate();
    return clock.on("change", invalidate);
  }, [clock, invalidate]);

  useEffect(() => () => shadow.dispose(), [shadow]);

  useEffect(() => {
    onReady();
  }, [onReady]);

  useFrame(() => {
    const root = overlay.current;
    if (!root || !worker || !lift) return;
    const find = <T extends SVGElement>(name: keyof Marks) =>
      root.querySelector<T>(`[data-mark="${name}"]`)!;
    const chapter = clock.get();
    if (chapter < 5.95) captured.current = false;
    const t = clamp((chapter - 1.02) / 0.94);
    const turning = Math.sin(Math.PI * t);
    const gait =
      Math.sin(t * Math.PI * 8) * 0.36 * Math.sin(Math.PI * t) ** 0.33;
    worker.position.set(
      personStart[0] + (personEnd[0] - personStart[0]) * t,
      Math.abs(gait) * 0.04,
      personStart[1] + (personEnd[1] - personStart[1]) * t,
    );
    lift.position.set(
      liftStart[0] + (liftEnd[0] - liftStart[0]) * t,
      0,
      liftStart[1] + (liftEnd[1] - liftStart[1]) * t,
    );
    worker.rotation.set(0, 0.59 + turning * 1.36, 0);
    lift.rotation.set(0, -0.61 - turning * 0.91, 0);
    workerShadow.current?.position.set(
      worker.position.x,
      0.012,
      worker.position.z,
    );
    liftShadow.current?.position.set(lift.position.x, 0.012, lift.position.z);
    liftShadow.current?.rotation.set(-Math.PI / 2, lift.rotation.y, 0, "YXZ");
    legs.forEach((part, index) => {
      if (part) part.rotation.x = gait * (index % 2 ? -1 : 1);
    });
    wheels.forEach((wheel) => {
      if (wheel) wheel.rotation.x = -t * 5.3;
    });
    const project = (point: Vector3) => {
      point.project(camera);
      return point.set(
        ((point.x + 1) * WIDTH) / 2,
        ((1 - point.y) * HEIGHT) / 2,
        0,
      );
    };
    const feet = (object: Object3D) =>
      project(new Vector3(object.position.x, 0.025, object.position.z));
    const person = feet(worker);
    const equipment = feet(lift);
    const detection = clamp(chapter * 1.3) * (1 - clamp(chapter - 5));
    const workerMark = find<SVGSVGElement>("worker");
    const liftMark = find<SVGSVGElement>("lift");
    if (detection > 0) {
      drawBox(workerMark, worker, project);
      drawBox(liftMark, lift, project);
    }
    opacity(workerMark, detection);
    opacity(liftMark, detection);
    opacity(find("trails"), t * clamp((3 - chapter) * 3));
    line(
      find("workerTrack"),
      project(new Vector3(personStart[0], 0.025, personStart[1])),
      person,
    );
    line(
      find("liftTrack"),
      project(new Vector3(liftStart[0], 0.025, liftStart[1])),
      equipment,
    );
    opacity(find("cameraSignal"), 1 - chapter);
    line(
      find("cameraLine"),
      project(new Vector3(-4.9, 2.94, -1.93)),
      project(new Vector3(-3.85, 2.43, -0.43)),
    );
    opacity(find("spatial"), (chapter - 2) * 1.4);
    find("zone").setAttribute(
      "points",
      zone
        .map(([x, z]) => {
          const v = project(new Vector3(x, 0.025, z));
          return `${v.x},${v.y}`;
        })
        .join(" "),
    );
    line(find("distance"), person, equipment);
    opacity(find("event"), (chapter - 4) * 1.28);
    find("eventPoint").setAttribute("cx", String((person.x + equipment.x) / 2));
    find("eventPoint").setAttribute("cy", String((person.y + equipment.y) / 2));
    if (chapter >= 5.99 && !captured.current) {
      captured.current = true;
      gl.render(renderScene, camera);
      const source = gl.domElement;
      const image = document.createElement("canvas");
      image.width = 520;
      image.height = 320;
      const center = (person.x + equipment.x) / (2 * WIDTH);
      image
        .getContext("2d")
        ?.drawImage(
          source,
          (center - 0.205) * source.width,
          0.29 * source.height,
          0.41 * source.width,
          0.38 * source.height,
          0,
          0,
          image.width,
          image.height,
        );
      onCapture(image.toDataURL("image/webp", 0.86));
    }
  });

  return (
    <>
      <primitive object={scene} />
      <mesh ref={workerShadow} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[0.9, 0.68]} />
        <meshBasicMaterial
          map={shadow}
          transparent
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      <mesh
        ref={liftShadow}
        rotation={[-Math.PI / 2, 0, 0]}
        rotation-order="YXZ"
      >
        <planeGeometry args={[2.85, 3.5]} />
        <meshBasicMaterial
          map={shadow}
          transparent
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      {[-3.95, -1.8, 2.1, 4.25].map((x) => (
        <mesh
          key={x}
          position={[x, 0.011, -2.23]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[3.0, 1.75]} />
          <meshBasicMaterial
            map={shadow}
            transparent
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      ))}
    </>
  );
}

export default function WarehouseCanvas({
  chapter,
  reduced,
  overlay,
  onReady,
  onCapture,
}: {
  chapter: number;
  reduced: boolean;
  overlay: RefObject<SVGSVGElement | null>;
  onReady: () => void;
  onCapture: (image: string) => void;
}) {
  const clock = useMotionValue(chapter);
  const camera = useMemo(() => {
    const halfWidth = 7.6;
    const halfHeight = (halfWidth * HEIGHT) / WIDTH;
    const view = new OrthographicCamera(
      -halfWidth,
      halfWidth,
      halfHeight,
      -halfHeight,
      0.1,
      70,
    );
    view.position.set(...cameraPosition);
    view.lookAt(0, 0.82, 0);
    view.updateMatrixWorld();
    return Object.assign(view, { manual: true });
  }, []);
  useEffect(() => {
    if (reduced) {
      clock.jump(chapter);
      return;
    }
    const transition = animate(clock, chapter, {
      duration: Math.min(1.5, 0.48 + Math.abs(chapter - clock.get()) * 0.37),
      ease: [0.42, 0, 0.22, 1],
    });
    return () => transition.stop();
  }, [chapter, clock, reduced]);

  return (
    <Canvas
      camera={camera}
      orthographic
      frameloop="demand"
      dpr={[1, 1.4]}
      gl={{
        alpha: true,
        antialias: true,
        powerPreference: "low-power",
        failIfMajorPerformanceCaveat: true,
      }}
    >
      <hemisphereLight args={["#ffffff", "#7889a2", 2.25]} />
      <directionalLight position={[-4, 9, 6]} intensity={2.8} />
      <directionalLight
        position={[6, 5, -4]}
        intensity={1.25}
        color="#e4ecff"
      />
      <Suspense fallback={null}>
        <Warehouse
          clock={clock}
          overlay={overlay}
          onReady={onReady}
          onCapture={onCapture}
        />
      </Suspense>
    </Canvas>
  );
}
