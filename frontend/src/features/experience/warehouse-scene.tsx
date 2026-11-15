"use client";

import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "motion/react";
import { useEffect, useId } from "react";

const rackPositions = [
  [116, 146],
  [194, 120],
  [467, 198],
  [545, 171],
];

function Rack({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d="M0 0 58-18 106 6 48 25Z" className="scene-rack-top" />
      <path d="M0 0v108l48 24V25Z" className="scene-rack-side" />
      <path d="M48 25v107l58-19V6Z" className="scene-rack-front" />
      <path
        d="M0 36l48 24 58-19M0 73l48 24 58-19M0 108V0m48 132V25m58 88V6"
        className="scene-rack-lines"
      />
      {[0, 35, 70].map((level) => (
        <g key={level} transform={`translate(0 ${level})`}>
          <path
            d="M54 27l21-7v20l-21 7zm27-9 19-6v20l-19 6z"
            className="scene-parcels"
          />
          <path d="M62 27v7m26-15v7" className="scene-package-lines" />
        </g>
      ))}
    </g>
  );
}

export function WarehouseScene({ chapter }: { chapter: number }) {
  const id = useId();
  const reduced = useReducedMotion();
  const progress = useMotionValue(0);
  useEffect(() => {
    if (reduced) {
      progress.jump(chapter);
      return;
    }
    const animation = animate(progress, chapter, {
      duration: Math.min(2.1, 0.63 + Math.abs(progress.get() - chapter) * 0.32),
      ease: [0.42, 0, 0.22, 1],
    });
    return () => animation.stop();
  }, [chapter, progress, reduced]);

  const observation = useTransform(progress, [0, 0.8], [1, 0]);
  const detection = useTransform(progress, [0.23, 1], [0, 1]);
  const tracking = useTransform(progress, [1.04, 2], [0, 1]);
  const context = useTransform(progress, [2.14, 3], [0, 1]);
  const event = useTransform(progress, [4.23, 5], [0, 1]);
  const capture = useTransform(progress, [5.04, 5.3, 6], [0, 1, 1]);
  const captureX = useTransform(progress, [5.32, 6], [260, 458]);
  const captureY = useTransform(progress, [5.32, 6], [176, 262]);
  const captureScale = useTransform(progress, [5.32, 6], [1, 1.18]);
  const backdrop = useTransform(progress, [5.33, 6], [1, 0.3]);
  const personX = useTransform(
    tracking,
    [0, 0.32, 0.7, 1],
    [234, 265, 300, 326],
  );
  const personY = useTransform(
    tracking,
    [0, 0.32, 0.7, 1],
    [312, 301, 284, 258],
  );
  const forkliftX = useTransform(
    tracking,
    [0, 0.34, 0.72, 1],
    [496, 461, 425, 399],
  );
  const forkliftY = useTransform(
    tracking,
    [0, 0.34, 0.72, 1],
    [327, 334, 321, 299],
  );
  const step = useTransform(tracking, (t) => Math.sin(t * Math.PI * 8) * 22);
  const oppositeStep = useTransform(step, (value) => -value);
  const wheel = useTransform(tracking, [0, 1], [0, -540]);

  return (
    <svg viewBox="0 0 760 488" className="warehouse-scene" aria-hidden="true">
      <defs>
        <pattern
          id={id}
          width="36"
          height="24"
          patternUnits="userSpaceOnUse"
          patternTransform="matrix(1 -.34 .92 .5 0 0)"
        >
          <path d="M36 0H0v24" fill="none" className="scene-grid" />
        </pattern>
      </defs>
      <motion.g style={{ opacity: backdrop }}>
        <g id={`${id}-bodega`}>
          <path
            d="M41 251 407 119 716 273 353 429Z"
            className="scene-foundation"
            transform="translate(0 10)"
          />
          <path d="M41 251 407 119 716 273 353 429Z" className="scene-floor" />
          <path d="M41 251 407 119 716 273 353 429Z" fill={`url(#${id})`} />
          <path
            d="m41 251 366-132V57L41 186Zm366-132 309 154v-65L407 57Z"
            className="scene-walls"
          />
          <path
            d="m41 186 366-129 309 151M41 216l366-129 309 151M102 165v64m244-151v64m118-56v62m190 31v62"
            className="scene-structure"
          />
          <path
            d="M84 267 446 137m-95 274 336-146m-536 10 209 107m31-12-212-106"
            className="scene-aisle"
          />
          <path
            d="M239 274 413 216 533 275 356 347Z"
            className="scene-zone-outline"
          />
          <motion.path
            d="M239 274 413 216 533 275 356 347Z"
            className="scene-zone"
            style={{ opacity: context }}
          />
          {rackPositions.map(([x, y]) => (
            <Rack key={x} x={x} y={y} />
          ))}
          <g className="scene-camera">
            <path d="M79 149v-40h23m-24 26 18-11" />
            <path d="m100 103 39-12 18 12-39 14Z" />
            <path d="m118 117 39-14v14l-39 14-18-13v-15Z" />
            <circle cx="146" cy="112" r="4" className="scene-camera-light" />
          </g>
          <motion.g style={{ opacity: observation }}>
            <path d="M148 114 224 254 411 189Z" className="scene-camera-cone" />
            <motion.path
              d="M148 114 216 85h120"
              className="scene-signal"
              style={{ pathLength: observation }}
            />
            <text x="224" y="74" className="scene-label">
              SEÑAL DE VIDEO
            </text>
          </motion.g>
          <motion.g style={{ opacity: tracking }}>
            <motion.path
              d="M234 312Q285 303 326 258"
              className="scene-trail"
              style={{ pathLength: tracking }}
            />
            <motion.path
              d="M496 327Q452 350 399 299"
              className="scene-trail scene-equipment-trail"
              style={{ pathLength: tracking }}
            />
          </motion.g>
          <motion.g style={{ x: personX, y: personY }}>
            <ellipse rx="14" ry="5" className="scene-object-shadow" />
            <motion.path
              d="M-4-18l-4 11-6 7h5"
              className="scene-person-limbs"
              style={{ rotate: step, transformOrigin: "-4px -18px" }}
            />
            <motion.path
              d="M6-18l3 10 6 8h-5"
              className="scene-person-limbs"
              style={{ rotate: oppositeStep, transformOrigin: "6px -18px" }}
            />
            <motion.path
              d="M-8-34l-5 10 2 6m19-16 6 9-1 6"
              className="scene-person-limbs"
              style={{ rotate: oppositeStep, transformOrigin: "0px -33px" }}
            />
            <path d="M-7-39q7-6 15 0l2 22H-9Z" className="scene-person-vest" />
            <path d="M-7-29h15" className="scene-vest-line" />
            <circle cy="-47" r="6" className="scene-person-face" />
            <path d="M-8-47a8 8 0 0 1 16 0z" className="scene-person-helmet" />
            <Detection
              progress={detection}
              label="PERSONA · P01"
              labelX={-84}
              labelY={-70}
              left={-24}
              top={-61}
              width={48}
              height={70}
            />
          </motion.g>
          <motion.g style={{ x: forkliftX, y: forkliftY }}>
            <ellipse cx="7" rx="44" ry="11" className="scene-object-shadow" />
            <path
              d="m-30-31 42-14 30 18-42 15Z"
              className="scene-forklift-top"
            />
            <path
              d="M-30-31v19L0 5v-17Zm30 19L42-27v18L0 5Z"
              className="scene-forklift-body"
            />
            <path
              d="m-13-45 23-8 19 10-23 8Zm0 0v19m19-9v20m23-28v20M-31-46v35l-20 8m25-7-18 8"
              className="scene-forklift-frame"
            />
            <path
              d="m-17-48 27-10 23 12-27 10Z"
              className="scene-forklift-top"
            />
            <circle cx="9" cy="1" r="8" className="scene-wheel" />
            <motion.path
              d="M5 1h8M9-3v8"
              className="scene-hub"
              style={{ rotate: wheel, transformOrigin: "9px 1px" }}
            />
            <circle cx="34" cy="-8" r="8" className="scene-wheel" />
            <motion.path
              d="M30-8h8m-4-4v8"
              className="scene-hub"
              style={{ rotate: wheel, transformOrigin: "34px -8px" }}
            />
            <path
              d="M-34-52v39l-28 9m27-1-24 10M2-13l28-10v8L2-5Z"
              className="scene-forklift-detail"
            />
            <Detection
              progress={detection}
              label="MONTACARGAS · F01"
              labelX={14}
              labelY={-72}
              left={-59}
              top={-66}
              width={110}
              height={80}
            />
          </motion.g>
          <motion.g style={{ opacity: context }}>
            <motion.path
              d="M326 258 399 299"
              className="scene-measure"
              style={{ pathLength: context }}
            />
            <circle cx="326" cy="258" r="3" className="scene-camera-light" />
            <circle cx="399" cy="299" r="3" className="scene-camera-light" />
            <text x="285" y="356" className="scene-label">
              ZONA DE TRÁNSITO
            </text>
          </motion.g>
          <motion.g style={{ opacity: event }}>
            <path d="M405 302h41l24 31h84" className="scene-signal" />
            <circle cx="405" cy="302" r="7" className="scene-event-dot" />
            <text x="474" y="324" className="scene-label">
              EVENTO REGISTRADO
            </text>
          </motion.g>
        </g>
      </motion.g>
      <motion.g
        style={{
          x: captureX,
          y: captureY,
          scale: captureScale,
          transformOrigin: "0px 0px",
          opacity: capture,
        }}
      >
        <svg
          width="220"
          height="165"
          viewBox="260 176 220 165"
          className="scene-capture"
        >
          <rect
            x="260"
            y="176"
            width="220"
            height="165"
            className="scene-floor"
          />
          <use href={`#${id}-bodega`} className="scene-capture-copy" />
          <rect
            x="261.5"
            y="177.5"
            width="217"
            height="162"
            rx="5"
            className="scene-capture-frame"
          />
        </svg>
      </motion.g>
    </svg>
  );
}

function Detection({
  progress,
  label,
  labelX,
  labelY,
  left,
  top,
  width,
  height,
}: {
  progress: ReturnType<typeof useMotionValue<number>>;
  label: string;
  labelX: number;
  labelY: number;
  left: number;
  top: number;
  width: number;
  height: number;
}) {
  return (
    <motion.g style={{ opacity: progress }}>
      <motion.rect
        x={left}
        y={top}
        width={width}
        height={height}
        rx="3"
        className="scene-detection"
        style={{ pathLength: progress }}
      />
      <path
        d={`M${labelX + (labelX < 0 ? 18 : 0)} ${labelY + 4} L${left + width / 2} ${top}`}
        className="scene-label-leader"
      />
      <text x={labelX} y={labelY} className="scene-label">
        {label}
      </text>
    </motion.g>
  );
}
