/** Shared helpers for the hand-rolled SVG charts. */

/** Round tick values covering [min, max], at roughly `target` intervals. */
export function ticks(min: number, max: number, target = 4): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const raw = span / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  // Snap the interval to something a person would choose: 1, 2, 2.5, 5 or 10.
  const step =
    magnitude * ([1, 2, 2.5, 5, 10].find((m) => raw <= m * magnitude) ?? 10);

  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    out.push(+v.toFixed(6));
  }
  return out;
}

/** Polyline through (x, y) points, skipping nulls so a series can start late. */
export function polyline(points: Array<[number, number] | null>): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (!p) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${p[0].toFixed(2)},${p[1].toFixed(2)} `;
    pen = true;
  }
  return d.trim();
}
