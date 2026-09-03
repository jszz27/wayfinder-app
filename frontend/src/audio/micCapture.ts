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
      return "마이크 사용 권한이 거부되었습니다. 브라우저 주소창의 자물쇠 아이콘에서 마이크를 허용해 주세요.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "사용할 수 있는 마이크를 찾지 못했습니다. 마이크가 연결되어 있는지 확인해 주세요.";
    case "NotReadableError":
      return "마이크를 다른 프로그램이 사용 중입니다. 해당 프로그램을 닫고 다시 시도해 주세요.";
    default:
      return "마이크를 시작하지 못했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.";
  }
}
