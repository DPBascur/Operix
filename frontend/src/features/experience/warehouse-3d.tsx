"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { motion, useTransform, type MotionValue } from "motion/react";
import { WarehouseScene } from "./warehouse-scene";
import type { WarehouseCapture } from "./warehouse-canvas";
import {
  captureBeat,
  dossierBeat,
  ramp,
  storyPose,
} from "./warehouse-timeline";
import {
  Component,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

const WarehouseCanvas = dynamic(() => import("./warehouse-canvas"), {
  ssr: false,
});

class WarehouseBoundary extends Component<
  { onUnavailable: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    console.warn("No se pudo inicializar la bodega 3D.", error.message);
    this.props.onUnavailable();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function DetectionLabel({
  name,
  role,
  id,
}: {
  name: string;
  role: string;
  id: string;
}) {
  return (
    <svg data-mark={name} className="warehouse-detection">
      <rect x="1" y="30" width="100%" className="warehouse-detection-box" />
      <rect
        x="1"
        y="1"
        width={role === "Persona" ? 149 : 185}
        height="29"
        rx="4"
        className="warehouse-detection-label"
      />
      <text x="9" y="21">
        {role} · {id}
      </text>
    </svg>
  );
}

function Evidence({
  frame,
  clock,
  reduced,
  chapter,
}: {
  frame: WarehouseCapture;
  clock: MotionValue<number>;
  reduced: boolean;
  chapter: number;
}) {
  const [x, y, w, h] = frame.bounds;
  const position = (from: number, to: number) => (beat: number) => {
    const t = storyPose(beat).evidence;
    return `${(from + (to - from) * t) * 100}%`;
  };
  const finalWidth = 0.35;
  const finalHeight = (finalWidth * h) / w;
  const finalTop = Math.min(0.49, 0.94 - finalHeight);
  const left = useTransform(clock, position(x, 0.6));
  const top = useTransform(clock, position(y, finalTop));
  const width = useTransform(clock, position(w, finalWidth));
  const height = useTransform(clock, position(h, finalHeight));
  const opacity = useTransform(clock, (beat) =>
    ramp(beat, captureBeat, captureBeat + 0.02),
  );
  const radius = useTransform(
    clock,
    (beat) => `${2 + 8 * ramp(beat, captureBeat, dossierBeat)}px`,
  );
  return (
    <motion.div
      className="warehouse-capture"
      style={
        reduced
          ? {
              left: "60%",
              top: position(y, finalTop)(6),
              width: "35%",
              height: position(h, finalHeight)(6),
              opacity: chapter === 6 ? 1 : 0,
            }
          : { left, top, width, height, opacity, borderRadius: radius }
      }
    >
      <Image src={frame.url} alt="" fill unoptimized />
    </motion.div>
  );
}

export function Warehouse3D({
  chapter,
  clock,
  reduced,
  onReady,
  onUnavailable,
}: {
  chapter: number;
  clock: MotionValue<number>;
  reduced: boolean;
  onReady?: () => void;
  onUnavailable: () => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const overlay = useRef<SVGSVGElement>(null);
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [ready, setReady] = useState(false);
  const [capture, setCapture] = useState<WarehouseCapture | null>(null);
  const [contextLost, setContextLost] = useState(false);
  const handleReady = useCallback(() => {
    setReady(true);
    onReady?.();
  }, [onReady]);
  const tint = useTransform(clock, [captureBeat, dossierBeat], [0, 0.19]);

  useEffect(() => {
    if (!surface.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(entry.isIntersecting);
      if (entry.isIntersecting) setMounted(true);
    });
    observer.observe(surface.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className="warehouse-3d"
      ref={surface}
      data-rendered={ready && !contextLost}
      data-chapter={chapter}
      aria-hidden="true"
    >
      <div className="warehouse-poster" hidden={ready || contextLost}>
        <Image
          src="/experience/warehouse-reference.webp"
          alt=""
          width={1200}
          height={800}
          unoptimized
          loading="eager"
        />
      </div>
      <svg
        ref={overlay}
        viewBox="0 0 900 600"
        className="warehouse-overlay"
        style={{ visibility: ready && !contextLost ? "visible" : "hidden" }}
      >
        <g data-mark="cameraSignal">
          <polygon data-mark="cameraCone" className="warehouse-cone" />
          <line data-mark="cameraLine" className="warehouse-signal" />
        </g>
        <g data-mark="spatial">
          <line data-mark="distance" className="warehouse-distance" />
        </g>
        <g data-mark="trails" className="warehouse-trails">
          <polyline data-mark="workerTrack" />
          <polyline data-mark="liftTrack" />
        </g>
        <DetectionLabel name="worker" role="Persona" id="P01" />
        <DetectionLabel name="lift" role="Montacargas" id="F01" />
        <g data-mark="event">
          <rect data-mark="captureFrame" rx="3" className="warehouse-frame" />
          <circle data-mark="eventPoint" r="11" className="warehouse-event" />
        </g>
      </svg>
      {mounted && (
        <div
          className="warehouse-renderer"
          style={{ visibility: contextLost ? "hidden" : "visible" }}
        >
          <WarehouseBoundary onUnavailable={onUnavailable}>
            <WarehouseCanvas
              chapter={chapter}
              clock={clock}
              reduced={reduced}
              suspended={!visible || contextLost}
              onContextChange={setContextLost}
              overlay={overlay}
              onReady={handleReady}
              onCapture={setCapture}
            />
          </WarehouseBoundary>
        </div>
      )}
      {contextLost && <WarehouseScene chapter={chapter} />}
      {ready && !contextLost && capture && (
        <motion.div
          className="warehouse-departure"
          style={{ opacity: reduced ? (chapter === 6 ? 0.19 : 0) : tint }}
        />
      )}
      {ready && !contextLost && capture && (
        <Evidence
          frame={capture}
          clock={clock}
          reduced={reduced}
          chapter={chapter}
        />
      )}
    </div>
  );
}
