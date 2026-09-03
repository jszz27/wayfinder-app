interface ScreenPillProps {
  sharing: boolean;
  busy: boolean;
  onTurnOn: () => void;
  onTurnOff: () => void;
}

// Plan.md section 8: guide mode reuses caption mode's pill pattern -- a
// muted label plus a small segmented control -- so both modes read as
// "tab, then sub-setting" rather than a stack of same-weight buttons.
//
// Turning it on is what triggers the browser's own share prompt
// (Plan.md section 10); there is no separate "share screen" button.
export function ScreenPill({ sharing, busy, onTurnOn, onTurnOff }: ScreenPillProps) {
  return (
    <div className="source-row">
      <span className="source-label" id="screen-label">
        Screen reference
      </span>
      <div className="source-pill" role="radiogroup" aria-labelledby="screen-label">
        <button
          type="button"
          role="radio"
          className="source-segment"
          aria-checked={sharing}
          disabled={busy}
          onClick={onTurnOn}
        >
          On
        </button>
        <button
          type="button"
          role="radio"
          className="source-segment"
          aria-checked={!sharing}
          disabled={busy}
          onClick={onTurnOff}
        >
          Off
        </button>
      </div>
      {sharing && (
        <span className="screen-live" role="status">
          Sharing
        </span>
      )}
    </div>
  );
}
