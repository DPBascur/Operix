"use client";

import { motion, useReducedMotion } from "motion/react";
import { useId } from "react";

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
  const glide = {
    duration: reduced ? 0 : 0.76,
    ease: [0.22, 1, 0.36, 1] as const,
  };
  const marks = { duration: reduced ? 0 : 0.44 };
  const tracking = chapter >= 2;
  const context = chapter >= 3;
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
        initial={false}
        animate={{ opacity: context ? 1 : 0 }}
        transition={marks}
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
      <motion.g
        initial={false}
        animate={{ opacity: chapter === 0 ? 1 : 0 }}
        transition={marks}
      >
        <path d="M148 114 224 254 411 189Z" className="scene-camera-cone" />
        <motion.path
          d="M148 114 216 85h120"
          className="scene-signal"
          initial={false}
          animate={{ pathLength: chapter === 0 ? 1 : 0 }}
          transition={glide}
        />
        <text x="224" y="74" className="scene-label">
          SEÑAL DE VIDEO
        </text>
      </motion.g>
      <motion.g
        initial={false}
        animate={{ opacity: tracking ? 1 : 0 }}
        transition={marks}
      >
        <motion.path
          d="M234 312q49-9 101-41"
          className="scene-trail"
          initial={false}
          animate={{ pathLength: tracking ? 1 : 0 }}
          transition={glide}
        />
        <motion.path
          d="M496 327q-50 9-106-26"
          className="scene-trail scene-equipment-trail"
          initial={false}
          animate={{ pathLength: tracking ? 1 : 0 }}
          transition={glide}
        />
      </motion.g>
      <motion.g
        initial={false}
        animate={{ x: tracking ? 335 : 234, y: tracking ? 271 : 312 }}
        transition={glide}
      >
        <ellipse rx="14" ry="5" className="scene-object-shadow" />
        <path
          d="m-4-18-6 17m16-17 3 17m-14-34-8 15m19-16 9 13"
          className="scene-person-limbs"
        />
        <path d="M-7-39q7-6 15 0l2 22H-9Z" className="scene-person-vest" />
        <path d="M-7-29h15" className="scene-vest-line" />
        <circle cy="-47" r="6" className="scene-person-face" />
        <path d="M-8-47a8 8 0 0 1 16 0z" className="scene-person-helmet" />
        <Detection
          visible={chapter >= 1}
          label="PERSONA · P01"
          left={-24}
          top={-61}
          width={48}
          height={70}
          reduced={Boolean(reduced)}
        />
      </motion.g>
      <motion.g
        initial={false}
        animate={{ x: tracking ? 390 : 496, y: tracking ? 301 : 327 }}
        transition={glide}
      >
        <ellipse cx="7" rx="44" ry="11" className="scene-object-shadow" />
        <path d="m-30-31 42-14 30 18-42 15Z" className="scene-forklift-top" />
        <path
          d="M-30-31v19L0 5v-17Zm30 19L42-27v18L0 5Z"
          className="scene-forklift-body"
        />
        <path
          d="m-13-45 23-8 19 10-23 8Zm0 0v19m19-9v20m23-28v20M-31-46v35l-20 8m25-7-18 8"
          className="scene-forklift-frame"
        />
        <path d="m-17-48 27-10 23 12-27 10Z" className="scene-forklift-top" />
        <circle cx="9" cy="1" r="7" className="scene-wheel" />
        <circle cx="34" cy="-8" r="7" className="scene-wheel" />
        <Detection
          visible={chapter >= 1}
          label="MONTACARGAS · F01"
          left={-59}
          top={-66}
          width={110}
          height={80}
          reduced={Boolean(reduced)}
        />
      </motion.g>
      <motion.g
        initial={false}
        animate={{ opacity: context ? 1 : 0 }}
        transition={marks}
      >
        <motion.path
          d="M335 271 390 301"
          className="scene-measure"
          initial={false}
          animate={{ pathLength: context ? 1 : 0 }}
          transition={glide}
        />
        <circle cx="335" cy="271" r="3" className="scene-camera-light" />
        <circle cx="390" cy="301" r="3" className="scene-camera-light" />
        <text x="285" y="356" className="scene-label">
          ZONA DE TRÁNSITO
        </text>
      </motion.g>
      <motion.g
        initial={false}
        animate={{ opacity: chapter >= 5 ? 1 : 0 }}
        transition={marks}
      >
        <path d="M405 302h41l24 31h84" className="scene-signal" />
        <circle cx="405" cy="302" r="7" className="scene-event-dot" />
        <text x="474" y="324" className="scene-label">
          EVENTO REGISTRADO
        </text>
      </motion.g>
    </svg>
  );
}

function Detection({
  visible,
  label,
  left,
  top,
  width,
  height,
  reduced,
}: {
  visible: boolean;
  label: string;
  left: number;
  top: number;
  width: number;
  height: number;
  reduced: boolean;
}) {
  return (
    <motion.g
      initial={false}
      animate={{ opacity: visible ? 1 : 0 }}
      transition={{ duration: reduced ? 0 : 0.25 }}
    >
      <motion.rect
        x={left}
        y={top}
        width={width}
        height={height}
        rx="3"
        className="scene-detection"
        initial={false}
        animate={{ pathLength: visible ? 1 : 0 }}
        transition={{ duration: reduced ? 0 : 0.48 }}
      />
      <text x={left} y={top - 7} className="scene-label">
        {label}
      </text>
    </motion.g>
  );
}
