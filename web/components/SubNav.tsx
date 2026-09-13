"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Tabs within a section — Drivers | Constructors under Standings. */
export function SubNav({
  links,
  label,
}: {
  links: { href: string; label: string }[];
  label: string;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="flex gap-1 rounded border border-line bg-panel p-1">
      {links.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`focus-ring rounded px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-colors ${
              active ? "bg-panel-high text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
