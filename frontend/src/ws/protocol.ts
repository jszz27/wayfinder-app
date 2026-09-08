// The WebSocket message set from Plan.md section 5. This file is the
// frontend's single source of truth for the wire format; it mirrors
// backend-ws/app/protocol.py field for field.

export type AudioSource = "mic" | "tab_audio";

export type ClientMessage =
  | { type: "audio_chunk"; data: string; seq: number; source: AudioSource }
  | { type: "end_stream" }
  // Added in Sprint 3: who this stream belongs to. Optional, and only
  // meaningful as the very first frame.
  | { type: "auth"; token: string };

export interface CaptionMessage {
  type: "caption";
  text: string;
  /** false marks an interim result that may still be revised. */
  is_final: boolean;
  /** Caption line ordinal; see docs/sprint-1.md. */
  seq: number;
  /**
   * BCP-47 tag the text was recognised as, present only when the language
   * was detected rather than configured. Null on every other path.
   */
  language?: string | null;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export interface StreamEndedMessage {
  type: "stream_ended";
  session_id: string;
}

export type ServerMessage = CaptionMessage | ErrorMessage | StreamEndedMessage;

/** Returns null for anything that is not a message the spec defines. */
export function parseServerMessage(raw: string): ServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;

  const message = value as Record<string, unknown>;
  switch (message.type) {
    case "caption":
      return typeof message.text === "string" &&
        typeof message.is_final === "boolean" &&
        typeof message.seq === "number"
        ? (message as unknown as CaptionMessage)
        : null;
    case "error":
      return typeof message.message === "string"
        ? (message as unknown as ErrorMessage)
        : null;
    case "stream_ended":
      return typeof message.session_id === "string"
        ? (message as unknown as StreamEndedMessage)
        : null;
    default:
      return null;
  }
}
