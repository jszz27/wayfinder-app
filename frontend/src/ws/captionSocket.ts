import {
  parseServerMessage,
  type AudioSource,
  type CaptionMessage,
  type ClientMessage,
} from "./protocol";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface CaptionSocketHandlers {
  onCaption: (caption: CaptionMessage) => void;
  onError: (message: string) => void;
  onStreamEnded: () => void;
  onConnectionChange: (state: ConnectionState) => void;
}

// Capped below 5 s so a dropped connection is back within the window the
// sprint's acceptance criteria call for (Plan.md section 12).
const RECONNECT_DELAYS_MS = [250, 500, 1000, 2000, 4000];

export class CaptionSocket {
  private socket: WebSocket | null = null;
  private attempt = 0;
  private reconnectTimer: number | null = null;
  private closedByUs = false;
  private everOpened = false;
  /** Kept across reconnects so the server sees one continuous sequence. */
  private seq = 0;

  constructor(
    private readonly url: string,
    private readonly source: AudioSource,
    private readonly handlers: CaptionSocketHandlers,
  ) {}

  /** Resolves once the first connection is established. */
  open(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.connect(resolve, reject);
    });
  }

  private connect(onFirstOpen?: () => void, onFirstFailure?: (e: Error) => void) {
    this.handlers.onConnectionChange(this.attempt === 0 ? "connecting" : "reconnecting");

    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.everOpened = true;
      this.handlers.onConnectionChange("open");
      onFirstOpen?.();
    };

    socket.onmessage = (event) => {
      const message = parseServerMessage(String(event.data));
      if (!message) return;

      if (message.type === "caption") {
        this.handlers.onCaption(message);
      } else if (message.type === "error") {
        this.handlers.onError(message.message);
      } else {
        // stream_ended is the server's acknowledgement of end_stream, so
        // the close that follows it is expected, not a dropped link.
        this.closedByUs = true;
        this.handlers.onStreamEnded();
      }
    };

    socket.onclose = () => {
      if (this.closedByUs) {
        this.handlers.onConnectionChange("closed");
        return;
      }
      if (onFirstFailure && !this.everOpened) {
        // Never connected in the first place: surface it instead of
        // silently retrying behind a "listening" label.
        this.handlers.onConnectionChange("closed");
        onFirstFailure(new Error("자막 서버에 연결하지 못했습니다."));
        return;
      }
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose always follows; reconnection is handled there.
    };
  }

  private scheduleReconnect() {
    const delay =
      RECONNECT_DELAYS_MS[Math.min(this.attempt, RECONNECT_DELAYS_MS.length - 1)] ??
      RECONNECT_DELAYS_MS[RECONNECT_DELAYS_MS.length - 1]!;
    this.attempt += 1;
    this.handlers.onConnectionChange("reconnecting");
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.closedByUs) this.connect();
    }, delay);
  }

  /** Audio recorded while the link is down is dropped, not queued. */
  sendAudioChunk(pcm: ArrayBuffer) {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.send({
      type: "audio_chunk",
      data: toBase64(pcm),
      seq: this.seq++,
      source: this.source,
    });
  }

  endStream() {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      this.close();
      return;
    }
    this.send({ type: "end_stream" });
  }

  /** Drops the connection without waiting for a stream_ended acknowledgement. */
  close() {
    this.closedByUs = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.handlers.onConnectionChange("closed");
  }

  private send(message: ClientMessage) {
    this.socket?.send(JSON.stringify(message));
  }
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const CHUNK = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}
