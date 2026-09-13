"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";

/**
 * Site-wide navigation, mounted once in the root layout.
 *
 * The logo is always a link home, on every surface — it is the affordance people reach
 * for first. The round frame is a ring on the mark itself rather than a wrapper, so it
 * stays crisp at nav size. The bar's height is fixed by --nav-h so pinned layouts
 * underneath can offset by it.
 */

export function Logo({
  size = 34,
  withWordmark = true,
  href = "/",
}: {
  size?: number;
  withWordmark?: boolean;
  href?: string | null;
}) {
  const mark = (
    <span className="flex items-center gap-2.5">
      <span
        className="relative shrink-0 overflow-hidden rounded-full ring-1 ring-line transition-[box-shadow,transform] duration-200 group-hover:ring-deploy"
        style={{ width: size, height: size }}
      >
        <Image
          src="/logo.png"
          alt=""
          width={size * 2}
          height={size * 2}
          priority
          className="h-full w-full object-cover"
        />
      </span>
      {withWordmark && (
        <span className="display text-sm tracking-[0.22em] text-ink">
          CLIPPING
        </span>
      )}
    </span>
  );

  if (!href) return mark;
  return (
    <Link
      href={href}
      aria-label="Clipping — back to the start"
      className="focus-ring group rounded-full"
    >
      {mark}
    </Link>
  );
}

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/standings/drivers", label: "Standings" },
  { href: "/drivers", label: "Drivers" },
  { href: "/teams", label: "Teams" },
  { href: "/energy", label: "Energy" },
];

/** A link owns its whole first path segment, so /standings/constructors lights "Standings". */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  const segment = "/" + href.split("/")[1];
  return pathname === segment || pathname.startsWith(segment + "/");
}

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-30 h-[var(--nav-h)] border-b border-line bg-surface/85 backdrop-blur-md">
      <div className="flex h-full items-center justify-between gap-4 px-4 sm:px-6">
        <Logo />
        <div className="flex min-w-0 items-center gap-1">
          {/* Scrolls sideways on narrow screens rather than collapsing into a menu:
              five links fit on a phone, and a hamburger hides the site map. */}
          <div className="flex items-center gap-1 overflow-x-auto whitespace-nowrap">
            {LINKS.map((link) => {
              const active = isActive(pathname, link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`focus-ring rounded px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                    active
                      ? "bg-panel-high text-ink"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
          <span className="mx-1 h-4 w-px shrink-0 bg-line" aria-hidden="true" />
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
