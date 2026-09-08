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
        Audio source
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
          Microphone
        </button>
        <button
          type="button"
          role="radio"
          className="source-segment"
          aria-checked={source === "tab_audio"}
          disabled={locked}
          title="Caption the sound from a tab or screen you share"
          onClick={() => onChange("tab_audio")}
        >
          Playing audio
        </button>
      </div>
    </div>
  );
}
