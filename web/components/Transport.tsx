"use client";

const SPEEDS = [0.25, 0.5, 1, 2, 4];

export function Transport({
  playing,
  speed,
  elapsed,
  total,
  onToggle,
  onRestart,
  onSpeed,
  onScrub,
}: {
  playing: boolean;
  speed: number;
  elapsed: number;
  total: number;
  onToggle: () => void;
  onRestart: () => void;
  onSpeed: (s: number) => void;
  onScrub: (fraction: number) => void;
}) {
  const fraction = total > 0 ? elapsed / total : 0;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        onClick={onToggle}
        className="focus-ring rounded border border-line bg-panel-high px-3 py-1.5 text-xs uppercase tracking-[0.14em] hover:border-muted transition-colors"
        aria-pressed={playing}
      >
        {playing ? "Pause" : "Play"}
      </button>
      <button
        onClick={onRestart}
        className="focus-ring rounded border border-line px-3 py-1.5 text-xs uppercase tracking-[0.14em] text-muted hover:text-ink hover:border-muted transition-colors"
      >
        Restart
      </button>

      <label className="flex items-center gap-2 flex-1 min-w-[220px]">
        <span className="sr-only">Lap position</span>
        <input
          type="range"
          min={0}
          max={1000}
          value={Math.round(fraction * 1000)}
          onChange={(e) => onScrub(Number(e.target.value) / 1000)}
          className="focus-ring w-full accent-deploy"
          aria-label="Scrub through the lap"
        />
      </label>

      <span className="tabular text-xs text-muted w-24 text-right">
        {elapsed.toFixed(2)}s / {total.toFixed(2)}s
      </span>

      <div className="flex items-center gap-1" role="group" aria-label="Playback speed">
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => onSpeed(s)}
            aria-pressed={speed === s}
            className={`focus-ring tabular rounded px-2 py-1 text-[11px] transition-colors ${
              speed === s
                ? "bg-line text-ink"
                : "text-muted hover:text-ink"
            }`}
          >
            {s}×
          </button>
        ))}
      </div>
    </div>
  );
}
