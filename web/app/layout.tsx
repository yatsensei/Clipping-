import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
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
  title: "Clipping — 2026 F1 energy deployment",
  description:
    "Where a 2026 Formula 1 car should deploy its battery around a lap, solved by " +
    "dynamic programming on a physics model fitted to real telemetry.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${archivo.variable} ${jetbrains.variable}`}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
