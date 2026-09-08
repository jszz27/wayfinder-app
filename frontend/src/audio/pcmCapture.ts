// Turning a MediaStream into the wire format backend-ws expects.
//
// Both caption sources end up here: a microphone and a shared tab differ
// only in how the browser hands over the stream, not in what has to be
// done with it afterwards (Plan.md section 9).

export const TARGET_SAMPLE_RATE = 16_000;
/** ~100 ms at 16 kHz -- the chunk size agreed with backend-ws. */
export const FRAMES_PER_CHUNK = 1_600;

const WORKLET_URL = "/pcm-worklet.js";

export interface AudioCapture {
  /** The rate the browser actually gave us, for diagnostics. */
  readonly contextSampleRate: number;
  stop(): Promise<void>;
}

/**
 * Feeds `stream` through the PCM worklet, handing 100 ms chunks to `onChunk`.
 *
 * Takes ownership of the stream: `stop()` ends every track on it, including
 * any the caller is not using.
 */
export async function captureFromStream(
  stream: MediaStream,
  onChunk: (pcm: ArrayBuffer) => void,
): Promise<AudioCapture> {
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
    // No output: captured audio must not be played back through the
    // speakers, which for a shared tab would also cause a feedback loop.
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
