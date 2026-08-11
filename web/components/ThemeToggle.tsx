"use client";

import { useEffect } from "react";
import { useTheme } from "@/lib/theme";

/**
 * Light/dark switch.
 *
 * The colour transition is enabled only after mount, via the `theme-ready` class. Without
 * that, applying the stored theme on first paint animates every surface on the page from
 * dark to light while the user watches it load.
 */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  useEffect(() => {
    document.documentElement.classList.add("theme-ready");
  }, []);

  const isDark = theme === "dark";

  return (
    <button
      onClick={toggle}
      role="switch"
      aria-checked={!isDark}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
      className="focus-ring group flex h-7 w-7 items-center justify-center rounded border border-line text-muted transition-colors hover:border-muted hover:text-ink"
    >
      {/* Sun and moon are swapped by opacity so the button never reflows. */}
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {isDark ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        ) : (
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        )}
      </svg>
    </button>
  );
}
