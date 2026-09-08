// Saving a session's captions as a plain text file.
//
// The point of the widget is that someone can follow a conversation they
// would otherwise miss; being able to keep what was said afterwards is the
// other half of that, so the file is a clean transcript with nothing added
// around it.

import type { CaptionLine } from "../useCaptionSession";

/** The captions as they read on screen, one line each, oldest first. */
export function buildTranscript(lines: CaptionLine[]): string {
  return lines
    .map((line) => line.text.trim())
    .filter((text) => text.length > 0)
    .join("\n");
}

/** `wayfinder-captions-2026-09-07-1432.txt` */
export function transcriptFilename(now: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `wayfinder-captions-${stamp}.txt`;
}

export function downloadTranscript(lines: CaptionLine[]): void {
  const text = buildTranscript(lines);
  if (!text) return;

  // A byte order mark, because these transcripts are often Korean and some
  // Windows editors still read a BOM-less file as the system codepage,
  // which turns the whole thing into mojibake.
  const blob = new Blob(["\ufeff", text, "\n"], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = transcriptFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();

  // Revoked on the next tick: revoking immediately can cancel the download
  // in some browsers before it has read the blob.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
