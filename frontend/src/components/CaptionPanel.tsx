import { useEffect, useRef } from "react";

import type { CaptionLine } from "../useCaptionSession";

interface CaptionPanelProps {
  lines: CaptionLine[];
  fontSize: number;
  placeholder: string;
}

// Plan.md section 8: the most recently confirmed line is bold, earlier
// lines fade. Interim text is kept visually distinct so a reader can tell
// what is still liable to change.
export function CaptionPanel({ lines, fontSize, placeholder }: CaptionPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [lines]);

  const confirmed = lines.filter((line) => line.isFinal);
  const interim = lines.find((line) => !line.isFinal);
  const lastConfirmedSeq = confirmed.at(-1)?.seq;

  return (
    <div
      className="caption-panel"
      style={{ fontSize: `${fontSize}px` }}
      ref={scrollRef}
      role="log"
      aria-live="polite"
      aria-label="실시간 자막"
    >
      {confirmed.length === 0 && !interim ? (
        <p className="caption-placeholder">{placeholder}</p>
      ) : (
        <>
          {confirmed.map((line) => (
            <p
              key={line.seq}
              className={
                line.seq === lastConfirmedSeq ? "caption-line is-latest" : "caption-line"
              }
            >
              {line.text}
            </p>
          ))}
          {interim && (
            <p className="caption-line is-interim">
              {interim.text}
              <span className="caption-cursor" aria-hidden="true" />
            </p>
          )}
        </>
      )}
    </div>
  );
}
