// Screen capture for guide mode (Plan.md section 10).
//
// Not a continuous watch: the stream stays open only so that a single
// frame can be grabbed at the moment a question is sent. Most multimodal
// APIs take one image, not video, and holding a live analysis loop over a
// screen that may show passwords is not something to do casually.

/** Long edge of the capture sent to the model. */
const MAX_EDGE = 1280;

/** JPEG rather than PNG: a screenshot of a UI compresses to a fraction of
 *  the size, which matters when it rides inside a JSON request body. */
const MIME = "image/jpeg";
const QUALITY = 0.72;

export interface ScreenShare {
  /** Grabs the current frame as a data URL, or null if the stream ended. */
  capture(): string | null;
  stop(): void;
}

export async function startScreenShare(
  onEndedByBrowser: () => void,
): Promise<ScreenShare> {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: false,
  });

  const video = document.createElement("video");
  video.srcObject = stream;
  video.muted = true;
  // Safari will not produce frames from a detached element in some
  // versions; keeping it in the document but invisible avoids that.
  video.style.position = "fixed";
  video.style.opacity = "0";
  video.style.pointerEvents = "none";
  video.style.width = "1px";
  video.style.height = "1px";
  document.body.appendChild(video);

  await video.play();

  let stopped = false;
  const teardown = () => {
    if (stopped) return;
    stopped = true;
    stream.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
    video.remove();
  };

  // The browser's own "Stop sharing" bar bypasses our UI entirely, so the
  // widget has to hear about it or the pill would keep claiming it is on.
  stream.getVideoTracks().forEach((track) => {
    track.addEventListener("ended", () => {
      teardown();
      onEndedByBrowser();
    });
  });

  return {
    capture() {
      if (stopped || video.videoWidth === 0) return null;

      const scale = Math.min(1, MAX_EDGE / Math.max(video.videoWidth, video.videoHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);

      const context = canvas.getContext("2d");
      if (!context) return null;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL(MIME, QUALITY);
    },
    stop: teardown,
  };
}

/** Turns a getDisplayMedia rejection into something worth showing a user. */
export function describeScreenError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  switch (name) {
    case "NotAllowedError":
      return "Screen sharing was cancelled. Turn it on again when you are ready.";
    case "NotFoundError":
      return "No screen or window was available to share.";
    case "NotSupportedError":
      return "This browser cannot share a screen. Try Chrome or Edge.";
    default:
      return "Could not start screen sharing. Refresh the page and try again.";
  }
}
