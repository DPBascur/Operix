"use client";

import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import type { MotionValue } from "motion/react";
import { Suspense, useEffect, useMemo, useRef, type RefObject } from "react";
import {
  Mesh,
  type MeshBasicMaterial,
  CanvasTexture,
  Vector3,
  type Object3D,
  OrthographicCamera,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

import { captureBeat, storyPaths, storyPose, unit } from "./warehouse-timeline";

const WIDTH = 900;
const HEIGHT = 600;
const halfWidth = 7.6;

export type WarehouseCapture = {
  url: string;
  bounds: readonly [left: number, top: number, width: number, height: number];
};

function frameCamera(
  camera: OrthographicCamera,
  shot: ReturnType<typeof storyPose>["shot"],
) {
  const [x, y, z, width, yaw, pitch] = shot;
  const radius = 20;
  const horizontal = radius * Math.cos(pitch);
  camera.position.set(
    x + Math.sin(yaw) * horizontal,
    y + Math.sin(pitch) * radius,
    z + Math.cos(yaw) * horizontal,
  );
  camera.lookAt(x, y, z);
  camera.zoom = (halfWidth * 2) / width;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
}

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
  workerTrack: SVGPolylineElement;
  liftTrack: SVGPolylineElement;
  cameraSignal: SVGGElement;
  cameraLine: SVGLineElement;
  spatial: SVGGElement;
  captureFrame: SVGRectElement;
  cameraCone: SVGPolygonElement;
  distance: SVGLineElement;
  event: SVGGElement;
  eventPoint: SVGCircleElement;
};

function opacity(node: SVGElement, value: number) {
  node.style.opacity = String(unit(value));
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
  svg.setAttribute("y", String(minY - 33));
  svg.setAttribute("width", String(maxX - minX + 6));
  svg.setAttribute("height", String(maxY - minY + 36));
  return { minX, maxX, minY, maxY };
}

function Warehouse({
  clock,
  chapter,
  reduced,
  suspended,
  onContextChange,
  overlay,
  onReady,
  onCapture,
}: {
  clock: MotionValue<number>;
  chapter: number;
  reduced: boolean;
  suspended: boolean;
  onContextChange: (lost: boolean) => void;
  overlay: RefObject<SVGSVGElement | null>;
  onReady: () => void;
  onCapture: (image: WarehouseCapture) => void;
}) {
  const { scene } = useLoader(
    GLTFLoader,
    "/experience/warehouse.glb",
    (loader) => loader.setMeshoptDecoder(MeshoptDecoder),
  );
  const { camera, invalidate, gl, scene: renderScene } = useThree();
  const captured = useRef(false);
  const zone = useRef<MeshBasicMaterial>(null);
  const point = useMemo(() => new Vector3(), []);
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
    if (!reduced && !suspended) return clock.on("change", invalidate);
  }, [chapter, clock, invalidate, reduced, suspended]);

  useEffect(() => () => shadow.dispose(), [shadow]);

  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (event: Event) => {
      event.preventDefault();
      onContextChange(true);
    };
    const restored = () => {
      onContextChange(false);
      invalidate();
    };
    canvas.addEventListener("webglcontextlost", lost);
    canvas.addEventListener("webglcontextrestored", restored);
    return () => {
      canvas.removeEventListener("webglcontextlost", lost);
      canvas.removeEventListener("webglcontextrestored", restored);
    };
  }, [gl, invalidate, onContextChange]);

  useEffect(() => {
    onReady();
  }, [onReady]);

  function draw(beat: number, takeCapture = false) {
    const root = overlay.current;
    if (!root || !worker || !lift || !(camera instanceof OrthographicCamera))
      return;
    const find = <T extends SVGElement>(name: keyof Marks) =>
      root.querySelector<T>(`[data-mark="${name}"]`)!;
    const pose = storyPose(beat);
    frameCamera(camera, pose.shot);
    const gait = pose.worker.gait * 0.38;
    worker.position.set(pose.worker.x, 0, pose.worker.z);
    lift.position.set(pose.equipment.x, 0, pose.equipment.z);
    worker.rotation.set(0, pose.worker.yaw, 0);
    lift.rotation.set(0, pose.equipment.yaw, 0);
    workerShadow.current?.position.set(
      worker.position.x,
      0.012,
      worker.position.z,
    );
    liftShadow.current?.position.set(lift.position.x, 0.012, lift.position.z);
    liftShadow.current?.rotation.set(-Math.PI / 2, lift.rotation.y, 0, "YXZ");
    legs.forEach((part, index) => {
      if (part)
        part.rotation.x = gait * (index % 2 ? -1 : 1) * (index < 2 ? 1 : -0.62);
    });
    const soleHeight = Math.min(
      ...legs
        .slice(0, 2)
        .map((leg) => leg?.localToWorld(point.set(0, -0.912, 0.06)).y ?? 0),
    );
    worker.position.setY(Math.max(-0.025, Math.min(0.09, -soleHeight)));
    wheels.forEach((wheel, index) => {
      if (wheel)
        wheel.rotation.set(
          pose.equipment.travel / (index < 2 ? 0.34 : 0.266),
          index < 2 ? 0 : pose.equipment.steering,
          0,
          "YXZ",
        );
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
    const workerMark = find<SVGSVGElement>("worker");
    const liftMark = find<SVGSVGElement>("lift");
    opacity(workerMark, pose.detection);
    opacity(liftMark, pose.detection);
    if (pose.detection > 0) {
      drawBox(workerMark, worker, project);
      drawBox(liftMark, lift, project);
    }

    opacity(find("trails"), pose.tracks);
    if (pose.tracks > 0) {
      const paths = storyPaths(pose.person, pose.forklift);
      (["workerTrack", "liftTrack"] as const).forEach((name, index) => {
        find(name).setAttribute(
          "points",
          paths[index]
            .map(({ x, z }) => {
              const p = project(point.set(x, 0.025, z));
              return `${p.x},${p.y}`;
            })
            .join(" "),
        );
      });
    }

    opacity(find("cameraSignal"), pose.cameraSignal);
    if (pose.cameraSignal > 0) {
      const lens = [-4.9, 2.94, -1.93] as const;
      line(
        find("cameraLine"),
        project(new Vector3(...lens)),
        project(new Vector3(-2.1, 0.08, 0.85)),
      );
      find("cameraCone").setAttribute(
        "points",
        [lens, [-2.25, 0.02, 1.7], [-0.95, 0.02, -0.04]]
          .map(([x, y, z]) => {
            const p = project(point.set(x, y, z));
            return `${p.x},${p.y}`;
          })
          .join(" "),
      );
    }

    if (zone.current)
      Object.assign(zone.current, { opacity: pose.spatial * 0.25 });
    opacity(find("spatial"), pose.spatial);
    line(find("distance"), person, equipment);
    opacity(find("event"), pose.event);
    const marker = find("eventPoint");
    marker.setAttribute("cx", String((person.x + equipment.x) / 2));
    marker.setAttribute("cy", String((person.y + equipment.y) / 2));

    const frameOpacity = pose.event * unit((beat - 4.84) / 0.22);
    const frame = find("captureFrame");
    opacity(frame, frameOpacity);
    if (frameOpacity > 0 || takeCapture) {
      const a = drawBox(workerMark, worker, project);
      const b = drawBox(liftMark, lift, project);
      const left = Math.max(0, Math.min(a.minX, b.minX) - 22);
      const top = Math.max(0, Math.min(a.minY, b.minY) - 22);
      const width = Math.min(WIDTH, Math.max(a.maxX, b.maxX) + 22) - left;
      const height = Math.min(HEIGHT, Math.max(a.maxY, b.maxY) + 22) - top;
      frame.setAttribute("x", String(left));
      frame.setAttribute("y", String(top));
      frame.setAttribute("width", String(width));
      frame.setAttribute("height", String(height));
      if (takeCapture) {
        gl.render(renderScene, camera);
        const source = gl.domElement;
        const image = document.createElement("canvas");
        image.width = 560;
        image.height = Math.round((image.width * height) / width);
        image
          .getContext("2d")
          ?.drawImage(
            source,
            (left / WIDTH) * source.width,
            (top / HEIGHT) * source.height,
            (width / WIDTH) * source.width,
            (height / HEIGHT) * source.height,
            0,
            0,
            image.width,
            image.height,
          );
        captured.current = true;
        onCapture({
          url: image.toDataURL("image/webp", 0.86),
          bounds: [left / WIDTH, top / HEIGHT, width / WIDTH, height / HEIGHT],
        });
      }
    }
  }

  useFrame(() => {
    if (suspended) return;
    const beat = reduced ? chapter : clock.get();
    if (!captured.current && beat >= captureBeat) draw(captureBeat, true);
    draw(beat);
  });

  return (
    <>
      <primitive object={scene} />
      <mesh position={[-0.025, 0.009, 0.45]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[5.15, 2.4]} />
        <meshBasicMaterial
          ref={zone}
          color="#2a78db"
          transparent
          depthWrite={false}
          opacity={0}
        />
      </mesh>
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
  clock,
  reduced,
  suspended,
  onContextChange,
  overlay,
  onReady,
  onCapture,
}: {
  chapter: number;
  clock: MotionValue<number>;
  reduced: boolean;
  suspended: boolean;
  onContextChange: (lost: boolean) => void;
  overlay: RefObject<SVGSVGElement | null>;
  onReady: () => void;
  onCapture: (image: WarehouseCapture) => void;
}) {
  const camera = useMemo(() => {
    const halfHeight = (halfWidth * HEIGHT) / WIDTH;
    const view = new OrthographicCamera(
      -halfWidth,
      halfWidth,
      halfHeight,
      -halfHeight,
      0.1,
      70,
    );
    frameCamera(view, storyPose(0).shot);
    return Object.assign(view, { manual: true });
  }, []);

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
          chapter={chapter}
          clock={clock}
          reduced={reduced}
          suspended={suspended}
          onContextChange={onContextChange}
          overlay={overlay}
          onReady={onReady}
          onCapture={onCapture}
        />
      </Suspense>
    </Canvas>
  );
}
