import manifest from "@/public/media/credits.json";

/**
 * The media manifest written by `scripts/fetch_media.py`, imported at build time.
 *
 * Whether a portrait exists is decided here, from the manifest, never by probing for a
 * 404 at runtime: a missing image is the designed path (rookies, trademarked logos), not
 * an error, and the fallback must render identically on the server and the client.
 */

export interface MediaCredit {
  file: string;
  title: string;
  license: string;
  license_url: string | null;
  author: string | null;
  source_url: string;
}

export interface MediaManifest {
  generated: string | null;
  drivers: Record<string, MediaCredit | null>;
  teams: Record<string, MediaCredit | null>;
  missing: Record<string, string>;
}

export const MEDIA: MediaManifest = manifest as MediaManifest;

export type MediaKind = "drivers" | "teams";

export function mediaFor(kind: MediaKind, id: string): MediaCredit | null {
  return MEDIA[kind][id] ?? null;
}

export function mediaUrl(credit: MediaCredit): string {
  return `/media/${credit.file}`;
}
