// Microphone capture for caption mode (Plan.md section 9).
//
// getUserMedia permission is granted once and persists, unlike tab audio,
// which needs the user to pick a tab every session.

export const TARGET_SAMPLE_RATE = 16_000;
/** ~100 ms at 16 kHz -- the chunk size agreed with backend-ws. */
export const FRAMES_PER_CHUNK = 1_600;

const WORKLET_URL = "/pcm-worklet.js";

export interface MicCapture {
  /** The rate the browser actually gave us, for diagnostics. */
  readonly contextSampleRate: number;
  stop(): Promise<void>;
}

export async function startMicCapture(
  onChunk: (pcm: ArrayBuffer) => void,
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  let context: AudioContext;
  try {
    context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  } catch {
    // Some browsers refuse a forced rate; the worklet resamples instead.
    context = new AudioContext();
  }

  try {
    await context.audioWorklet.addModule(WORKLET_URL);
  } catch (error) {
    stream.getTracks().forEach((track) => track.stop());
    await context.close();
    throw error;
  }

  const source = context.createMediaStreamSource(stream);
  const chunker = new AudioWorkletNode(context, "pcm-chunker", {
    numberOfInputs: 1,
    // No output: the mic must not be played back through the speakers.
    numberOfOutputs: 0,
    processorOptions: {
      targetSampleRate: TARGET_SAMPLE_RATE,
      framesPerChunk: FRAMES_PER_CHUNK,
    },
  });

  chunker.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    onChunk(event.data);
  };
  source.connect(chunker);

  if (context.state === "suspended") {
    await context.resume();
  }

  return {
    contextSampleRate: context.sampleRate,
    async stop() {
      chunker.port.onmessage = null;
      source.disconnect();
      chunker.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      await context.close();
    },
  };
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
