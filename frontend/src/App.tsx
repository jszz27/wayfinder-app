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

export default function App() {
  const [mode, setMode] = useState<Mode>("caption");
  const [source, setSource] = useState<AudioSource>("mic");
  const [fontSize, setFontSize] = useState<number>(FONT_SIZES[1]);

  const { status, lines, notice, start, stop, dismissNotice } = useCaptionSession(source);
  const running = status !== "idle";

  return (
    <main className="widget">
      <ModeTabs mode={mode} onChange={setMode} />

      {mode === "caption" ? (
        <>
          {/* The audio source is fixed for the whole session (Plan.md
              section 5), so the control locks while a stream is open. */}
          <SourcePill source={source} onChange={setSource} locked={running} />
          <p className="status-text" aria-live="polite">
            {STATUS_TEXT[status]}
          </p>

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
