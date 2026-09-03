import type { AudioSource } from "../ws/protocol";

interface SourcePillProps {
  source: AudioSource;
  onChange: (source: AudioSource) => void;
  locked: boolean;
}

// Plan.md section 8: the audio source is a sub-setting inside caption
// mode, deliberately lighter and smaller than the tabs above it so it
// does not read as another mode.
export function SourcePill({ source, onChange, locked }: SourcePillProps) {
  return (
    <div className="source-row">
      <span className="source-label" id="source-label">
        음성 소스
      </span>
      <div className="source-pill" role="radiogroup" aria-labelledby="source-label">
        <button
          type="button"
          role="radio"
          className="source-segment"
          aria-checked={source === "mic"}
          disabled={locked}
          onClick={() => onChange("mic")}
        >
          마이크
        </button>
        <button
          type="button"
          role="radio"
          className="source-segment"
          aria-checked={source === "tab_audio"}
          // Tab audio capture lands with Plan.md section 9; the control is
          // shown now so the hierarchy is not rearranged later.
          disabled
          title="재생 중인 오디오 캡처는 다음 스프린트에서 추가됩니다."
        >
          재생 중인 오디오
        </button>
      </div>
    </div>
  );
}
