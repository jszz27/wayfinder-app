// Captioning the audio the user is already listening to (Plan.md section 9).
//
// The case this exists for: a video with no captions, or automatic ones
// that are not good enough. Rather than holding a microphone up to the
// speakers, the browser hands over the audio directly.
//
// Constraints that come from the browser, not from us (section 9):
//   - the user must choose what to share every session; there is no way to
//     remember the choice in a web app
//   - Chromium only. Safari has essentially no support
//   - what can be shared depends on the platform. Sharing a tab gives that
//     tab's audio anywhere; sharing a whole screen offers system audio on
//     Windows, but macOS cannot capture audio from a native app at all

import { captureFromStream, type AudioCapture } from "./pcmCapture";

export interface TabAudioCapture extends AudioCapture {
  /** What the user actually picked, for the status line. */
  readonly label: string;
}

/** Raised when the share succeeded but carried no audio track. */
export class NoSharedAudioError extends Error {
  constructor() {
    super("no audio track in the shared stream");
    this.name = "NoSharedAudioError";
  }
}

export async function startTabAudioCapture(
  onChunk: (pcm: ArrayBuffer) => void,
  onShareEnded: () => void,
): Promise<TabAudioCapture> {
  // Audio alone is not offered by getDisplayMedia: video has to be
  // requested for the browser to show the audio option at all.
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: true,
  });

  const [audio] = stream.getAudioTracks();
  if (!audio) {
    // The picker was answered but the audio box was left unticked, which
    // is easy to do and produces silence rather than an obvious failure.
    stream.getTracks().forEach((track) => track.stop());
    throw new NoSharedAudioError();
  }

  // The video track is left running on purpose. Stopping it is enough to
  // end the whole capture in some Chromium versions, taking the audio with
  // it, and nothing here reads the frames.
  const capture = await captureFromStream(stream, onChunk);

  // The browser's own "Stop sharing" bar bypasses this widget entirely, so
  // the session has to hear about it or it would sit silent forever.
  audio.addEventListener("ended", onShareEnded);

  return {
    contextSampleRate: capture.contextSampleRate,
    label: audio.label || "shared audio",
    async stop() {
      audio.removeEventListener("ended", onShareEnded);
      await capture.stop();
    },
  };
}

/** Turns a getDisplayMedia rejection into something worth showing a user. */
export function describeTabAudioError(error: unknown): string {
  if (error instanceof NoSharedAudioError) {
    return (
      "That share did not include any sound. Choose the tab again and turn " +
      'on "Also share tab audio" in the dialog.'
    );
  }
  const name = error instanceof DOMException ? error.name : "";
  switch (name) {
    case "NotAllowedError":
      return "Sharing was cancelled, so there is no audio to caption.";
    case "NotFoundError":
      return "There was nothing available to share.";
    case "NotSupportedError":
      return "This browser cannot capture playing audio. Try Chrome or Edge.";
    default:
      return "Could not capture the playing audio. Refresh the page and try again.";
  }
}
