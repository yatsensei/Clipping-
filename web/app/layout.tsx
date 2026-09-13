import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { Nav } from "@/components/Nav";
import { SiteFooter } from "@/components/SiteFooter";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

/*
  Typography per the brief: a wide grotesque for display, a monospace with true tabular
  figures for telemetry. Deliberately NOT an imitation of the official F1 brand face —
  that reads as pastiche and is someone else's trademark. This should look like an
  internal race engineering tool.
*/
const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  axes: ["wdth"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Clipping — F1 analytics",
    template: "%s — Clipping",
  },
  description:
    "Formula 1 analytics: live 2026 standings, driver and team profiles, and a " +
    "physics-based optimiser for where a 2026 car should deploy its battery around a lap.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      // The inline script below writes data-theme before React sees the document.
      suppressHydrationWarning
      className={`${archivo.variable} ${jetbrains.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      {/* No background on body — it lives on html (see globals.css). */}
      <body className="flex min-h-screen flex-col antialiased">
        <Nav />
        <div className="flex-1">{children}</div>
        <SiteFooter />
        <Analytics />
      </body>
    </html>
  );
}
