import {
  parseServerMessage,
  type AudioSource,
  type CaptionMessage,
  type ClientMessage,
} from "./protocol";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

/** Fetches the token to open a connection with, or null when signed out.
 *
 * A function rather than a value because it is called again for every
 * reconnect: a long recording can outlive the token it started with, and
 * a stale one would be refused just as the link came back.
 */
export type TokenSource = () => Promise<string | null>;

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
  /** True once this connection has said who it belongs to. */
  private ready = false;
  /** Kept across reconnects so the server sees one continuous sequence. */
  private seq = 0;

  constructor(
    private readonly url: string,
    private readonly source: AudioSource,
    private readonly handlers: CaptionSocketHandlers,
    private readonly getToken: TokenSource = async () => null,
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

    socket.onopen = async () => {
      this.attempt = 0;
      this.everOpened = true;

      // Plan.md section 5: auth is the opening frame or nothing, so it
      // goes out before the connection is reported open and before any
      // audio can be queued behind it. Signed out there is no frame at
      // all, which is what anonymous captioning looks like on the wire.
      const token = await this.getToken().catch(() => null);
      if (socket !== this.socket || socket.readyState !== WebSocket.OPEN) return;
      if (token) this.send({ type: "auth", token });

      this.ready = true;
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
      this.ready = false;
      if (this.closedByUs) {
        this.handlers.onConnectionChange("closed");
        return;
      }
      if (onFirstFailure && !this.everOpened) {
        // Never connected in the first place: surface it instead of
        // silently retrying behind a "listening" label.
        this.handlers.onConnectionChange("closed");
        onFirstFailure(new Error("Could not connect to the caption server."));
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

  /** Audio recorded while the link is down is dropped, not queued.
   *
   * That now includes the moment between a connection opening and its
   * auth frame going out: a chunk that overtook it would make the server
   * read the whole stream as anonymous, and the transcript would stop
   * being saved without anything appearing to go wrong.
   */
  sendAudioChunk(pcm: ArrayBuffer) {
    if (!this.ready || this.socket?.readyState !== WebSocket.OPEN) return;
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
