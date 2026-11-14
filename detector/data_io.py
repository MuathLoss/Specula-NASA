"""Read original aligned observations and package exact bytes; no image edits."""
import csv
import io
from pathlib import Path
import shutil
import zipfile
from contextlib import contextmanager

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


class Images:
    def __init__(self, root, patch):
        self.root, self.patch = root, patch
        self.archives = []
        self.index = {}
        paths = set((root / 'images_aligned').glob(f'aligned_{patch}*.zip'))
        paths.update(root.glob(f'aligned_{patch}*.zip'))
        paths.update(root.parent.glob(f'aligned_{patch}*.zip'))
        for path in sorted(paths):
            z = zipfile.ZipFile(path)
            self.archives.append(z)
            for info in z.infolist():
                if info.filename.lower().endswith('.fits'):
                    name = Path(info.filename).name
                    if name in self.index:
                        raise ValueError(f'Ambiguous duplicate FITS basename in archives: {name}')
                    self.index[name] = (z, info)

    def locate(self, row):
        name = row['file']
        if Path(name).name != name or '\\' in name:
            raise ValueError('Unsafe frame basename in table')
        p = self.root / 'data' / 'aligned' / self.patch / name
        if p.is_file():
            return p
        return self.index.get(name)

    @contextmanager
    def open(self, row):
        src = self.locate(row)
        if src is None:
            raise FileNotFoundError(row['file'])
        if isinstance(src, Path):
            with src.open('rb') as f:
                yield f
        else:
            z, info = src
            with z.open(info) as f:
                yield f

    def copy(self, row, output):
        # Copy exact original bytes, including every PSF/EPSF plane and header.
        dest = f'data/aligned/{self.patch}/{row["file"]}'
        with self.open(row) as src, output.open(dest, 'w', force_zip64=True) as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)

    def close(self):
        for z in self.archives:
            z.close()


def load_layers(images, row):
    with images.open(row) as stream, fits.open(stream, memmap=False) as h:
        science = np.asarray(h['SCI'].data, dtype=float)
        err = np.asarray(h['ERR'].data, dtype=float)
        wave = np.array(h['WAVE'].data, dtype=float)
        mask = np.asarray(h['MASK'].data)
        if not (science.shape == err.shape == wave.shape == mask.shape) or science.ndim != 2:
            raise ValueError('Invalid layer shapes')
        # Saturation is disallowed for subtraction compatibility, even though it
        # may still be useful for explicitly flagged positional tracking.
        good = (np.isfinite(science) & np.isfinite(err) & (err > 0)
                & np.isfinite(wave) & (wave > 0) & ((mask & 25) == 0))
        wcs = WCS(h['SCI'].header).celestial
        if not wcs.has_celestial:
            raise ValueError('Missing celestial WCS')
        has_psf = any(v.name.upper() in ('PSF', 'EPSF') for v in h)
        return wave, good, wcs, has_psf


def csv_text(rows, fields=None):
    s = io.StringIO(newline='')
    w = csv.DictWriter(s, fieldnames=fields or list(rows[0]), extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return s.getvalue()

