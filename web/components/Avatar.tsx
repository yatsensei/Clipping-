import Image from "next/image";
import { mediaFor, mediaUrl, type MediaKind } from "@/lib/media";
import { teamVars } from "@/lib/teams";

/**
 * A driver portrait or team logo, or initials on the team colour when there is none.
 *
 * Server-safe: no hooks, and the presence check reads the build-time manifest. Team
 * logos sit on a pale tile in BOTH themes: wordmarks are drawn for light backgrounds
 * (McLaren's is black on transparent), and a logo on the team colour reads as a blob.
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
          round ? "ring-1 ring-line" : "bg-[#f4f4f1] ring-1 ring-line"
        } ${className}`}
        // Percentage padding resolves against the PARENT's width, so it is in pixels.
        style={{ width: size, height: size, padding: round ? 0 : Math.round(size * 0.12) }}
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
