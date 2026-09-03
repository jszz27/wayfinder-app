import { useState } from "react";

import { CaptionPanel } from "./components/CaptionPanel";
import { ModeTabs, type Mode } from "./components/ModeTabs";
import { SettingsBar, FONT_SIZES } from "./components/SettingsBar";
import { SourcePill } from "./components/SourcePill";
import { useCaptionSession, type SessionStatus } from "./useCaptionSession";
import type { AudioSource } from "./ws/protocol";

const STATUS_TEXT: Record<SessionStatus, string> = {
  idle: "Press Start to begin listening through your microphone.",
  starting: "Preparing the microphone…",
  listening: "Listening through the microphone…",
  reconnecting: "Connection lost. Reconnecting…",
  stopping: "Finishing up…",
};

/** Renders a BCP-47 tag as a language name, e.g. ko-KR -> Korean.
 *
 * Only the primary subtag is named, because the full tag reads as a
 * dialect -- "American English", "Korean (South Korea)" -- which is more
 * than the chip is claiming. Mandarin is reported as cmn, which
 * Intl.DisplayNames does not know by that name.
 */
function languageName(tag: string): string {
  const primary = tag.split("-")[0] ?? tag;
  const forDisplay = primary === "cmn" || primary === "yue" ? "zh" : primary;
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(forDisplay) ?? tag;
  } catch {
    return tag;
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>("caption");
  const [source, setSource] = useState<AudioSource>("mic");
  const [fontSize, setFontSize] = useState<number>(FONT_SIZES[1]);

  const { status, lines, notice, language, start, stop, dismissNotice } =
    useCaptionSession(source);
  const running = status !== "idle";

  return (
    <main className="widget">
      <ModeTabs mode={mode} onChange={setMode} />

      {mode === "caption" ? (
        <>
          {/* The audio source is fixed for the whole session (Plan.md
              section 5), so the control locks while a stream is open. */}
          <SourcePill source={source} onChange={setSource} locked={running} />
          <div className="status-row">
            <p className="status-text" aria-live="polite">
              {STATUS_TEXT[status]}
            </p>
            {language && (
              <span className="language-chip" aria-live="polite">
                {languageName(language)}
              </span>
            )}
          </div>

          <CaptionPanel
            lines={lines}
            fontSize={fontSize}
            placeholder="Captions will appear here."
          />

          {notice && (
            <div className="notice" role="alert">
              <span>{notice}</span>
              <button type="button" className="notice-dismiss" onClick={dismissNotice}>
                Dismiss
              </button>
            </div>
          )}

          <button
            type="button"
            className={running ? "primary-button is-running" : "primary-button"}
            onClick={() => void (running ? stop() : start())}
            disabled={status === "starting" || status === "stopping"}
          >
            {running ? "Stop" : "Start"}
          </button>

          <SettingsBar fontSize={fontSize} onFontSizeChange={setFontSize} />
        </>
      ) : (
        <p className="placeholder-pane">Digital guide mode arrives in a later sprint.</p>
      )}
    </main>
  );
}
