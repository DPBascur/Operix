import type { CSSProperties } from "react";
import styles from "./effects.module.css";

type SplitTextProps = {
  text: string;
  as?: "span" | "p" | "h1" | "h2" | "h3";
  by?: "word" | "character";
  className?: string;
  animate?: boolean;
  staggerMs?: number;
};

const graphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

export function SplitText({
  text,
  as: Tag = "span",
  by = "word",
  className,
  animate = true,
  staggerMs = 35,
}: SplitTextProps) {
  const delay = Number.isFinite(staggerMs) ? Math.max(0, staggerMs) : 0;
  let index = 0;

  return (
    <Tag className={[styles.split, className].filter(Boolean).join(" ")}>
      <span className={styles.screenReaderText}>{text}</span>
      <span
        aria-hidden="true"
        data-animated={animate}
        className={styles.splitVisual}
      >
        {text.split(/(\s+)/u).map((token, tokenIndex) => {
          if (!token || /^\s+$/u.test(token)) return token;
          const units =
            by === "character"
              ? Array.from(graphemes.segment(token), ({ segment }) => segment)
              : [token];
          return (
            <span key={tokenIndex} className={styles.splitWord}>
              {units.map((unit, unitIndex) => (
                <span
                  key={unitIndex}
                  className={styles.splitUnit}
                  style={
                    {
                      "--split-delay": `${Math.min(index++ * delay, 700)}ms`,
                    } as CSSProperties
                  }
                >
                  {unit}
                </span>
              ))}
            </span>
          );
        })}
      </span>
    </Tag>
  );
}
