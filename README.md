# Specula

**Finding what moves in NASA's SPHEREx sky, and proving the answer is right.**

NASA Space Apps Challenge 2026 · Challenge: *Planet X and SPHEREx* · Team Specula

- **Website:** https://specula-nasa.vercel.app
- **Slides:** [Specula demo (PDF)](docs/Specula_slides.pdf) · [also on Google Drive](https://drive.google.com/file/d/11MxGnqrJZYOtJUa6BB8lM7PtCDD5RwxR/view?usp=sharing)

## What it does

NASA's SPHEREx telescope photographs the whole sky in infrared. Somewhere in those photos, things are moving: asteroids, comets, maybe a Planet X. They all look the same: a dot that changes place between photos.

Stars are like parked cars: same spot in every photo. Asteroids and comets are like people walking: a new spot each time. Specula takes real SPHEREx photos from NASA, removes everything that stays still, links the dots that move into tracks, and checks every track against NASA JPL's catalogue. The website lets you flip through the photos, see each moving object circled, and follow its orbit around the Sun in 3D.

NASA publishes new SPHEREx photos every week, and the same steps can search each release.

## Results

Tested on 1,401 real SPHEREx photos (99.2 GB) across five patches of sky.

| Test | Result |
|---|---|
| **3I/ATLAS**, the interstellar comet | found in **50 photos**, **0 false alarms**, median **2.8″** from NASA JPL's position |
| **Ceres** | found in **134 of 273 photos**, **0 false alarms**, median **0.58″** from JPL |
| **Known asteroids** | 20 Massalia, 232 Russia and 207 Hedda recovered as tracks |
| **False-alarm control** (North Ecliptic Pole, where no known object passes) | **0 tracks** |
| **New objects** | none: everything that moved is already in NASA's catalogue |

Honest limits:
- 3I/ATLAS is clearly visible in about 207 of its 258 photos, and we found it in 50 (24%). Along the way: the detector measured it in 180 photos, 131 of those spots survived star removal and burst grouping, and 50 joined the final track (8 of its 45 bursts).
- Known-asteroid photos recovered, by brightness: **41/66** brighter than magnitude 15, **16/34** at 15–17, **0/73** fainter than 17. Fainter objects need stacked photos, which we have not built yet.

### How we kept the test fair

1. The 3I/ATLAS answer key never reached the detector. Its patch is shifted off the comet at random, so the comet isn't always in the middle.
2. The linking settings were **locked before any 3I/ATLAS run**. The fingerprint of the locked code is in [`linking/`](linking).
3. The bar for a real track comes from running the same steps on **scrambled data**, where real motion can't survive. We added this step after the lock and say so in [`linking/README.md`](linking/README.md).

## How it works

```
NASA/IPAC IRSA: SPHEREx photos          NASA JPL: orbits, positions, known objects
            │                                         │
            ▼                                         │
  pipeline/   download → verify → crop → clean → align → difference → known-object labels
            │
            ▼
  detector/   measures every bright spot in every photo (1.9 million spots)
            │
            ▼
  linking/    removes stars → groups each burst → links bursts into tracks → noise test
            │
            ▼
  pipeline/   matches tracks to known objects, builds the website's data pack
            │
            ▼
  site/       the website: photo viewer + 3D solar system
```

## Repository

| Folder | What's inside |
|---|---|
| [`site/`](site) | The website (Next.js, React, Three.js). Its data pack is in `site/public/data/` |
| [`pipeline/`](pipeline) | From NASA's archive to clean, aligned, labelled photos, then the website's data files. Includes the photo lists, logs, NASA JPL labels and reference data, and the notebook where it started |
| [`detector/`](detector) | The detector: finds and measures bright spots in each photo, with tests, plus its full output (1.9 million spots) |
| [`linking/`](linking) | Turns spots into tracks: the locked code, every real and scrambled run, the tuning experiments, and the 3I/ATLAS scores |
| [`docs/`](docs) | The project story, the pipeline plan, the data formats, and what each teammate received |

### The SPHEREx photos

The photos are too big for GitHub (99.2 GB as downloaded), so the repo holds everything needed to fetch them from NASA instead. [`pipeline/manifest_all.csv`](pipeline/manifest_all.csv) lists all 1,401 photos with their NASA download links, and **[`REPRODUCE.md`](REPRODUCE.md)** walks through every step, from downloading them to the website, with the result you should see at each step.

## Run the website

Needs Node.js 20 or newer.

```bash
cd site
npm ci
npm run dev        # http://localhost:3000
```

No database or keys are needed: the site reads static files from `site/public/data/`.

## Rebuild everything

**[`REPRODUCE.md`](REPRODUCE.md)** has the exact steps: download the photos from NASA, prepare them, label known objects with NASA JPL, run the detector, link the spots into tracks, and build the website data. You need Python 3.11+ and about 160 GB of free disk.

Shortcut: our detector output is in the repo, so the tracks and scores can be rebuilt without downloading any photos (step 8 of the guide, about 5 minutes). We checked that it reproduces our tracks byte for byte.

## Team

| Name | Role |
|---|---|
| Muath Omar Alamoudi | Data pipeline |
| Omar Teskyeh | Motion detector |
| Abdullah Zuhair Balila | Integrations |
| Reham Ali Abdullah Modhesh | UI design |
| Amira Ibrahim | Frontend support |
| Mohammed Fuad Abdullah | Research and presentation |

## Data and tools

**NASA data**
- SPHEREx photos (QR2 + QR3): [NASA/IPAC Infrared Science Archive (IRSA)](https://irsa.ipac.caltech.edu/Missions/spherex.html)
- [SPHEREx mission, NASA JPL](https://www.jpl.nasa.gov/missions/spherex/)
- Orbits: [JPL Small-Body Database API](https://ssd-api.jpl.nasa.gov/doc/sbdb.html) and [SBDB Query API](https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html)
- Positions: [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/)
- Known objects in each photo: [JPL sb_ident API](https://ssd-api.jpl.nasa.gov/doc/sb_ident.html)

**Other**
- Background stars in 3D: [Yale Bright Star Catalogue](https://github.com/brettonw/YaleBrightStarCatalog)
- Website: Next.js, React, TypeScript, Three.js, React Three Fiber, drei, Zustand, Tailwind CSS, IBM Plex fonts, hosted on Vercel. Full list: [`site/package.json`](site/package.json)
- Data and detector: Python with NumPy, SciPy, pandas, Astropy, Pillow and Matplotlib. Lists: [`pipeline/requirements.txt`](pipeline/requirements.txt), [`detector/requirements.txt`](detector/requirements.txt)

## AI use

Parts of our code, documentation and slides were written with help from Claude (Anthropic). Every result was checked by the team against NASA JPL data.

## License

[MIT](LICENSE)
