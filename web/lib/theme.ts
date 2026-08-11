"use client";

import { useCallback, useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

export const THEME_KEY = "clipping-theme";

/**
 * The theme lives on `<html data-theme>`, not in React state.
 *
 * An inline script in the layout sets it before first paint, so there is no flash of the
 * wrong theme and no hydration mismatch — the server-rendered markup never contains a
 * colour, only CSS variable references that resolve differently under each theme.
 *
 * useSyncExternalStore rather than useState + effect: the attribute IS the source of
 * truth, and reading it in an effect would render once with the wrong answer.
 */
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

function getSnapshot(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

// Dark is the design's home, and the inline script corrects this before paint.
function getServerSnapshot(): Theme {
  return "dark";
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setTheme = useCallback((next: Theme) => {
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Private browsing or blocked storage: the choice simply will not persist.
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme(getSnapshot() === "dark" ? "light" : "dark");
  }, [setTheme]);

  return { theme, setTheme, toggle };
}

/**
 * Runs before paint, inlined in the document head.
 *
 * Respects a stored choice first, then the OS preference. Kept deliberately tiny and
 * dependency-free because it blocks rendering.
 */
export const THEME_INIT_SCRIPT = `
try {
  var stored = localStorage.getItem(${JSON.stringify(THEME_KEY)});
  var theme = stored || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.dataset.theme = theme;
} catch (e) {
  document.documentElement.dataset.theme = 'dark';
}
`.trim();
