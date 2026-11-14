# Specula

Frontend for team Specula (NASA Space Apps 2026, 14–15 Nov). A Next.js app
that reads the shared data pack from `public/data/` and renders a 2D SPHEREx
sky viewer plus a heliocentric 3D scene.

The UI runs entirely from those static files. Neon is optional, for storing
detection tracks or a seeded object catalog later (v0.3).

## Setup

Needs Node 20 or newer.

```bash
npm install
npm run dev
```

The dev server is at http://localhost:3000. Overview is `/`, the sky viewer
is `/viewer`, and the 3D scene is `/cosmos`. Patch, burst, and object
selection are shared across those routes.

```bash
npm run build
npm start
```

## Data pack

`public/data/` has the v0.1 images and per-patch JSON, the v0.2 3D files,
and the v0.3 `detections.json`, `scoring.json`, and `manifest.json`
(pack version 0.3). Do not edit those files; ask Muath if something in
the pack is wrong.

The viewer loads `detections.json`. Track ids that start with `MOCK-` stay
out of the demo. `detections_mock.json` remains so the candidate distance
check can still run. Known tracks are drawn as circles and linked to
`orbits.json` by `object_id`. With no candidates, the pipeline panel says
so instead of showing an empty candidate list.

`nep-cats-eye` is still missing thumbs and composites in this copy; `full/`
frames and `timeline.json` are present. The other four patches are complete.
The sky viewer shows a placeholder when a WebP is missing.

Check the orbit solver against the pack's two-body answers:

```bash
npm run test:orbit
```

The script exits 0 and skips if `orbits.json` or `reference_positions.json`
is not installed.

## Scripts

| Command                           | What it does                                              |
| --------------------------------- | --------------------------------------------------------- |
| `npm run dev`                     | Next.js dev server                                        |
| `npm run build`                   | Production build                                          |
| `npm start`                       | Serve the production build                                |
| `npm run lint`                    | ESLint                                                    |
| `npm run format` / `format:check` | Prettier                                                  |
| `npm run test:orbit`              | Compare `orbitPosition` to `reference_positions.json`     |
| `npm run test:detections`         | Check the v0.3 tracks, scores, and wording                |
| `npm run db:push`                 | Push the optional Drizzle schema to Neon                  |
| `npm run db:seed`                 | Seed objects, history, and detections from `public/data/` |

## Optional Neon

The site does not read the database. If you later want a place to keep v0.3
detection tracks or a copy of `objects.csv`:

1. Create a Neon project on the free tier: https://console.neon.tech
2. Copy `.env.example` to `.env` and set `DATABASE_URL` to the pooled
   connection string (ends with `-pooler`).
3. Run `npm run db:push`, or apply `scripts/schema.sql` in the Neon SQL editor.
4. Run `npm run db:seed`.

No Neon account is created by this repo.

## Hosting (free)

**App: Vercel Hobby.** Import the GitHub repo, set the root directory to
`site`, framework preset Next.js. No env vars are required for the
static UI.

`orbits.json` and `reference_positions.json` are in this data folder. A
public deploy will serve them to anyone with the site link.

**Database (optional): Neon free tier**, as above. Add `DATABASE_URL` in the
Vercel project settings only if you use the seed path.

## Environment

| Variable       | Required | Purpose                                   |
| -------------- | -------- | ----------------------------------------- |
| `DATABASE_URL` | no       | Neon pooled URI for `db:push` / `db:seed` |

## Stack

Next.js (App Router) and TypeScript, Tailwind CSS, Zustand, Three.js via
`@react-three/fiber` and `@react-three/drei`. Optional `drizzle-orm` with
`@neondatabase/serverless`.

## Wording

Say "candidate", never "discovery". Say "recovered" for an object the
pipeline matched to the NASA catalogue. This pack is a validation run:
settings were locked, and the noise threshold comes from scrambled data.
Sizes and candidate distances are ranges labelled estimated / approximate.
Say "latest published", not "live".

## Open

- The Movers view is still a yes/no for Muath (about 30–40 MB extra).
