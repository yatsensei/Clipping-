# web

Frontend for [Clipping](../README.md) — Next.js 16, TypeScript, Tailwind 4.

Two surfaces, deliberately different in energy:

- `/` — the landing page. Scroll position is lap distance: the car advances along Monza's
  real GPS trace, the outline draws itself, and the copy follows the naive strategy
  emptying its battery and clipping. The background is a WebGL field driven by state of
  charge, not by time.
- `/analysis` — the tool. Calm and dense: track map coloured by deployment, animated car
  marker with synchronised speed, power and state-of-charge traces, and a strategy
  toggle.

## Running

The API must be running first, from the repository root:

```bash
uv run uvicorn api.main:app --reload
```

Then:

```bash
npm install
npm run dev
```

Point elsewhere with `NEXT_PUBLIC_API_BASE` if the API is not on
`http://127.0.0.1:8000`.

## Checks

```bash
npm run lint
npm run build
npm test      # animation timing and scroll mapping
```

The tests cover the timing and scroll maths specifically because those failures are
invisible: a car advancing at a constant index per frame still looks like it is lapping,
it is simply wrong about where it should be.
