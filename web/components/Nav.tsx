"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Shared navigation.
 *
 * The logo is always a link home, on every surface — it is the affordance people reach
 * for first, and the analysis view previously had no way back to the landing page at all.
 * The round frame is a ring on the mark itself rather than a wrapper, so it stays crisp
 * at nav size.
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
        className="relative shrink-0 overflow-hidden rounded-full ring-1 ring-[#262A30] transition-[box-shadow,transform] duration-200 group-hover:ring-[#FF2E17]"
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
        <span className="display text-sm tracking-[0.22em] text-[#F2F0EB]">
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
  { href: "/", label: "The problem" },
  { href: "/analysis", label: "Analysis" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-30 border-b border-[#262A30] bg-[#08090A]/85 backdrop-blur-md">
      <div className="flex items-center justify-between gap-4 px-4 py-2.5 sm:px-6">
        <Logo />
        <div className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`focus-ring rounded px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                  active
                    ? "bg-[#1C1F24] text-[#F2F0EB]"
                    : "text-[#6B7280] hover:text-[#F2F0EB]"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
