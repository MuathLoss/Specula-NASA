# Third-party data, code and licenses

Specula's own code, docs and data products are under the [MIT License](LICENSE). Everything below comes from others. Each item is either NASA data or under an open-source license approved by the Open Source Initiative (OSI).

## NASA data

| Source | What we use it for | Terms |
|---|---|---|
| SPHEREx photos (QR2 + QR3), [NASA/IPAC Infrared Science Archive (IRSA)](https://irsa.ipac.caltech.edu/Missions/spherex.html) | The 1,401 photos everything is built on | Public NASA data, free to use. Credit: NASA/IPAC Infrared Science Archive and the SPHEREx mission |
| [JPL Small-Body Database API](https://ssd-api.jpl.nasa.gov/doc/sbdb.html) and [SBDB Query API](https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html) | Orbits of asteroids, Ceres, 3I/ATLAS and every known comet | Public NASA JPL service |
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | True positions of planets, Ceres, 3I/ATLAS and SPHEREx itself | Public NASA JPL service |
| [JPL sb_ident API](https://ssd-api.jpl.nasa.gov/doc/sb_ident.html) | Which known objects are inside each photo | Public NASA JPL service |

## Other data

| Source | What we use it for | License |
|---|---|---|
| Yale Bright Star Catalogue, 5th edition (Hoffleit and Warren), in the JSON version by Bretton Wade: [github.com/brettonw/YaleBrightStarCatalog](https://github.com/brettonw/YaleBrightStarCatalog) | Background stars in the 3D view (`pipeline/data/v02/bsc5/`, `site/public/data/cosmos.json`) | MIT (notice below) |

## Fonts

| Font | Where | License |
|---|---|---|
| [IBM Plex Sans and IBM Plex Mono](https://github.com/IBM/plex) (IBM Corp.), served through Google Fonts | Website and slides | SIL Open Font License 1.1 |

## Website libraries (`site/package.json`)

| Library | License |
|---|---|
| Next.js, React, React DOM | MIT |
| Three.js, React Three Fiber, drei | MIT |
| Zustand | MIT |
| Tailwind CSS, @tailwindcss/turbopack | MIT |
| @neondatabase/serverless, drizzle-kit | MIT |
| drizzle-orm | Apache-2.0 |
| TypeScript | Apache-2.0 |
| ESLint, eslint-config-next, eslint-config-prettier, Prettier, prettier-plugin-tailwindcss, tsx, @types/* | MIT |

## Python libraries (`pipeline/requirements.txt`, `detector/requirements.txt`)

| Library | License |
|---|---|
| NumPy | BSD-3-Clause |
| SciPy | BSD-3-Clause |
| pandas | BSD-3-Clause |
| Astropy | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| Matplotlib | Matplotlib License (PSF-based) |

## Tools we used (nothing of theirs is included in this repo)

| Tool | What for |
|---|---|
| [Vercel](https://vercel.com) | Hosting the website |
| [Claude](https://claude.ai) (Anthropic) | AI assistant: parts of our code, documentation and slides were written with its help, and every result was checked by the team against NASA JPL data |

---

### MIT License notice: Yale Bright Star Catalogue in JSON

```
MIT License

Copyright (c) 2016 Bretton Wade

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
