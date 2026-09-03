import { useState } from "react";

import { CaptionPanel } from "./components/CaptionPanel";
import { ModeTabs, type Mode } from "./components/ModeTabs";
import { SettingsBar, FONT_SIZES } from "./components/SettingsBar";
import { SourcePill } from "./components/SourcePill";
import { useCaptionSession, type SessionStatus } from "./useCaptionSession";
import type { AudioSource } from "./ws/protocol";

const STATUS_TEXT: Record<SessionStatus, string> = {
  idle: "시작을 누르면 마이크로 듣기 시작합니다.",
  starting: "마이크를 준비하는 중…",
  listening: "마이크로 듣는 중…",
  reconnecting: "연결이 끊겨 다시 연결하는 중…",
  stopping: "마무리하는 중…",
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
            placeholder="자막이 여기에 표시됩니다."
          />

          {notice && (
            <div className="notice" role="alert">
              <span>{notice}</span>
              <button type="button" className="notice-dismiss" onClick={dismissNotice}>
                닫기
              </button>
            </div>
          )}

          <button
            type="button"
            className={running ? "primary-button is-running" : "primary-button"}
            onClick={() => void (running ? stop() : start())}
            disabled={status === "starting" || status === "stopping"}
          >
            {running ? "중지" : "시작"}
          </button>

          <SettingsBar fontSize={fontSize} onFontSizeChange={setFontSize} />
        </>
      ) : (
        <p className="placeholder-pane">디지털 가이드 모드는 다음 스프린트에서 추가됩니다.</p>
      )}
    </main>
  );
}
