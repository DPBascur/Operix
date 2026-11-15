"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { motion } from "motion/react";
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
      <rect x="1" y="26" width="100%" className="warehouse-detection-box" />
      <rect
        x="1"
        y="1"
        width={role === "PERSONA" ? 117 : 167}
        height="25"
        rx="4"
        className="warehouse-detection-label"
      />
      <text x="9" y="18">
        {role} · {id}
      </text>
    </svg>
  );
}

export function Warehouse3D({
  chapter,
  reduced,
  onUnavailable,
}: {
  chapter: number;
  reduced: boolean;
  onUnavailable: () => void;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const overlay = useRef<SVGSVGElement>(null);
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [ready, setReady] = useState(false);
  const [capture, setCapture] = useState<string | null>(null);
  const handleReady = useCallback(() => setReady(true), []);

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
      data-rendered={ready}
      data-chapter={chapter}
      aria-hidden="true"
    >
      <div className="warehouse-poster" hidden={ready}>
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
        style={{ visibility: ready ? "visible" : "hidden" }}
      >
        <g data-mark="cameraSignal">
          <line data-mark="cameraLine" className="warehouse-signal" />
        </g>
        <g data-mark="spatial">
          <polygon data-mark="zone" className="warehouse-zone" />
          <line data-mark="distance" className="warehouse-distance" />
        </g>
        <g data-mark="trails" className="warehouse-trails">
          <line data-mark="workerTrack" />
          <line data-mark="liftTrack" />
        </g>
        <DetectionLabel name="worker" role="PERSONA" id="P01" />
        <DetectionLabel name="lift" role="MONTACARGAS" id="F01" />
        <g data-mark="event">
          <circle data-mark="eventPoint" r="11" className="warehouse-event" />
        </g>
      </svg>
      {mounted && (
        <div className="warehouse-renderer">
          <WarehouseBoundary onUnavailable={onUnavailable}>
            <WarehouseCanvas
              chapter={chapter}
              reduced={reduced || !visible}
              overlay={overlay}
              onReady={handleReady}
              onCapture={setCapture}
            />
          </WarehouseBoundary>
        </div>
      )}
      {ready && chapter === 6 && capture && (
        <motion.div
          className="warehouse-capture"
          initial={reduced ? false : { scale: 0.78, x: 18, opacity: 0.65 }}
          animate={{ scale: 1, x: 0, opacity: 1 }}
          transition={{ duration: reduced ? 0 : 0.5 }}
        >
          <Image src={capture} alt="" width={520} height={320} unoptimized />
          <span>Fotograma ilustrativo del evento</span>
        </motion.div>
      )}
    </div>
  );
}
