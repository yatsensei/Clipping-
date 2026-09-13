# web

Frontend for [Clipping](../README.md) — Next.js 16, TypeScript, Tailwind 4. No other
runtime dependencies: charts are hand-rolled SVG, animation is CSS and
`requestAnimationFrame`, the landing background is raw WebGL.

## Sections

- `/` — home: live leaders of both championships, the last race, a countdown to the
  next, and the energy-deployment problem in plain language.
- `/standings/drivers`, `/standings/constructors` — every completed round's table with a
  scrubber; rows glide to their new places (FLIP by hand), a points chart carries the
  cursor.
- `/drivers/[id]`, `/teams/[id]` — profiles: season results, position sparkline,
  teammate head-to-head. Generated on first visit, revalidated hourly.
- `/energy` — the landing for the optimiser. Scroll position is lap distance: the car
  advances along Monza's real GPS trace, the outline draws itself, and the copy follows
  the naive strategy emptying its battery and clipping.
- `/energy/analysis` — the tool. Track map coloured by deployment, animated car marker
  with synchronised speed, power and state-of-charge traces, and a strategy toggle.
- `/credits` — image licences and data sources.

## Data

- Live pages read Jolpica-F1 through `lib/f1/jolpica.ts` (server-only; limiter, retries,
  per-URL `revalidate`). Page-level composition is in `lib/f1/queries.ts`; every
  transform is a pure function in `lib/f1/standings.ts`.
- Energy pages read the committed snapshot in `public/api/` — `lib/server-data.ts` on the
  server, `lib/api.ts` in the browser. Set `NEXT_PUBLIC_API_BASE` to use the live FastAPI
  instead.
- Portraits and logos live in `public/media/` with `credits.json` as the manifest;
  `components/Avatar.tsx` falls back to initials when an entry is null.

## Running

```bash
npm install
npm run dev
```

## Checks

```bash
npm run lint
npm run build
npm test
```

The standings tests run against real API captures in `lib/f1/__fixtures__/` because the
failures that matter are the data's surprises, not the arithmetic. The animation tests
cover timing and scroll maths because those failures are invisible: a car advancing at a
constant index per frame still looks like it is lapping, it is simply wrong about where
it should be.
