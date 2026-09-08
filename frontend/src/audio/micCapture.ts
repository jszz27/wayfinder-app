// Microphone capture for caption mode (Plan.md section 9).
//
// getUserMedia permission is granted once and persists, unlike playing
// audio, which needs the user to pick what to share every session.

import { captureFromStream, type AudioCapture } from "./pcmCapture";

export { FRAMES_PER_CHUNK, TARGET_SAMPLE_RATE, type AudioCapture } from "./pcmCapture";

export async function startMicCapture(
  onChunk: (pcm: ArrayBuffer) => void,
): Promise<AudioCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  return captureFromStream(stream, onChunk);
}

/** Turns a getUserMedia rejection into something worth showing a user. */
export function describeMicError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone access was denied. Allow it from the lock icon in your browser's address bar.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone was found. Check that one is connected.";
    case "NotReadableError":
      return "Another application is using the microphone. Close it and try again.";
    default:
      return "Could not start the microphone. Refresh the page and try again.";
  }
}
