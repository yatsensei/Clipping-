import Image from "next/image";
import { mediaFor, mediaUrl, type MediaKind } from "@/lib/media";
import { teamVars } from "@/lib/teams";

/**
 * A driver portrait or team logo, or initials on the team colour when there is none.
 *
 * Server-safe: no hooks, and the presence check reads the build-time manifest. Team
 * logos are shown on a neutral panel rather than the team colour, because a logo is
 * already in its own colours and doubling them reads as a blob.
 */
export function Avatar({
  kind,
  id,
  label,
  teamId,
  size = 40,
  className = "",
}: {
  kind: MediaKind;
  id: string;
  /** Used for alt text and to derive initials. */
  label: string;
  teamId: string;
  size?: number;
  className?: string;
}) {
  const credit = mediaFor(kind, id);
  const round = kind === "drivers";
  const shape = round ? "rounded-full" : "rounded-md";

  if (credit) {
    const svg = credit.file.endsWith(".svg");
    return (
      <span
        className={`relative inline-block shrink-0 overflow-hidden ${shape} ${
          round ? "ring-1 ring-line" : "bg-panel-high p-[12%]"
        } ${className}`}
        style={{ width: size, height: size }}
      >
        <Image
          src={mediaUrl(credit)}
          alt={label}
          width={size * 2}
          height={size * 2}
          unoptimized={svg}
          className={`h-full w-full ${round ? "object-cover" : "object-contain"}`}
        />
      </span>
    );
  }

  return (
    <span
      aria-label={label}
      role="img"
      className={`team-bar inline-flex shrink-0 select-none items-center justify-center ${shape} font-sans font-semibold ${className}`}
      style={{ ...teamVars(teamId), width: size, height: size, fontSize: size * 0.36 }}
    >
      {initials(label, kind)}
    </span>
  );
}

function initials(label: string, kind: MediaKind): string {
  const words = label.trim().split(/\s+/);
  if (kind === "teams") return words[0].slice(0, 3).toUpperCase();
  return words
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}
