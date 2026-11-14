"""Conservative Specula v0.5 motion-detector baseline; not discovery validation."""
from dataclasses import dataclass, field
from pathlib import Path
from math import floor

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import maximum_filter, distance_transform_edt
from scipy.optimize import least_squares


@dataclass
class Config:
    snr_threshold: float = 5.0
    centroid_floor_px: float = 0.15
    max_sources_per_frame: int = 300
    edge_margin_px: int = 3
    saturated_centroid_floor_px: float = 0.5


@dataclass
class Frame:
    row: dict
    path: Path
    kind: str
    data: np.ndarray
    err: np.ndarray
    snr: np.ndarray
    mask: np.ndarray
    wave: np.ndarray | None
    wcs: WCS
    detections: list = field(default_factory=list)
    alignment: dict = field(default_factory=dict)
    noise_scale: float = 1.0


def detector_name(value):
    """Specula tables use D4 while real FITS headers use integer 4."""
    text = str(value).strip().upper()
    if text.startswith('D'):
        text = text[1:]
    if text not in {'1', '2', '3', '4', '5', '6'}:
        raise ValueError(f'Invalid detector identifier: {value!r}')
    return 'D' + text


def robust_scale(a):
    a = np.asarray(a)
    a = a[np.isfinite(a)]
    if a.size < 20:
        return 1.0
    med = np.median(a)
    return max(1.0, float(1.4826 * np.median(np.abs(a - med))))


def load_frame(root, row, forced_kind=None):
    root = Path(root)
    if Path(row['file']).name != row['file']:
        raise ValueError('Frame file must be a basename')
    kind = forced_kind or ('aligned' if row['patch'] in ('ceres', '3i-atlas') else 'diff')
    path = root / 'data' / kind / row['patch'] / row['file']
    with fits.open(path, memmap=False) as h:
        names = ('DIFF', 'DIFF_ERR', 'DIFF_SNR') if kind == 'diff' else ('SCI', 'ERR', 'SNR')
        data, err, snr = [np.array(h[n].data, dtype=float) for n in names]
        raw_mask = np.asarray(h['MASK'].data)
        if raw_mask.dtype.kind not in 'iu':
            raise ValueError(f'{path}: MASK must be integer')
        mask = raw_mask.astype(np.uint16)
        header = h[names[0]].header
        if data.ndim != 2 or not (data.shape == err.shape == snr.shape == mask.shape):
            raise ValueError(f'{path}: inconsistent 2-D layers')
        for key, col in [('GRID_ID', 'grid_id'), ('DETECTOR', 'detector'), ('PATCH', 'patch')]:
            normalize = detector_name if key == 'DETECTOR' else lambda v: str(v).strip()
            if key in header and normalize(header[key]) != normalize(row[col]):
                raise ValueError(f'{path}: header/table mismatch for {key}')
        wcs = WCS(header).celestial
        if not wcs.has_celestial:
            raise ValueError(f'{path}: celestial WCS required')
        if not np.isfinite(float(row['t_mid_mjd'])):
            raise ValueError(f'{path}: invalid observation time')
        if 'MJD-BEG' in header and 'MJD-END' in header:
            mid = (float(header['MJD-BEG']) + float(header['MJD-END'])) / 2
            if abs(mid - float(row['t_mid_mjd'])) * 86400 > 2:
                raise ValueError(f'{path}: header/table time mismatch exceeds 2 seconds')
        if kind == 'aligned':
            data -= float(header.get('BKG_MED', 0.0))  # ZODI already removed upstream.
        wave = np.array(h['WAVE'].data, dtype=float) if 'WAVE' in h else None
        if wave is not None and wave.shape != data.shape:
            raise ValueError(f'{path}: WAVE shape mismatch')
    good = np.isfinite(data) & np.isfinite(err) & (err > 0) & ((mask & 9) == 0)
    if np.count_nonzero(good) < 25:
        raise ValueError(f'{path}: insufficient usable pixels')
    # Recompute using provided errors. Never treat ERR as variance.
    snr = np.divide(data, err, out=np.full_like(data, np.nan), where=good)
    background = good & ((mask & (4 | 16 | 32)) == 0)
    scale = robust_scale(snr[background])
    return Frame(dict(row), path, kind, data, err, snr, mask, wave, wcs,
                 noise_scale=scale)


def _nearby_accepted(cells, x, y):
    """Exact original <1 pixel test, restricted to the only possible grid cells."""
    ix, iy = floor(x), floor(y)
    return any(np.hypot(px-x, py-y) < 1
               for bx in range(ix-1, ix+2) for by in range(iy-1, iy+2)
               for px, py in cells.get((bx, by), ()))


def detect(frame, cfg):
    """Peak detection + approximate Gaussian centroid; no min-area veto at 1px FWHM."""
    good = np.isfinite(frame.snr) & ((frame.mask & 9) == 0)
    # Distance includes array edges, not just bad pixels inside the footprint.
    distance = distance_transform_edt(np.pad(good, 1))[1:-1, 1:-1]
    score = np.where(good, frame.snr / frame.noise_scale, -np.inf)
    peaks = (score == maximum_filter(score, size=3, mode='constant', cval=-np.inf))
    yy, xx = np.where(peaks & (score >= cfg.snr_threshold) &
                      (distance > cfg.edge_margin_px))
    order = np.argsort(score[yy, xx])[::-1]
    if len(order) > cfg.max_sources_per_frame:
        raise ValueError(f'{frame.path}: {len(order)} peaks exceeds cap; raise '
                         '--max-sources-per-frame explicitly; no silent truncation')
    results = []
    accepted_cells = {}
    for k in order:
        x, y = int(xx[k]), int(yy[k])
        sy, sx = slice(y-2, y+3), slice(x-2, x+3)
        values, errors = frame.data[sy, sx], frame.err[sy, sx] * frame.noise_scale
        bits = int(np.bitwise_or.reduce(frame.mask[sy, sx].ravel()))
        saturated = bool(bits & 16)
        valid = np.isfinite(values) & np.isfinite(errors) & (errors > 0)
        # Unsaturated pixels define the local baseline. A saturated source is
        # retained with an explicitly approximate moment centroid, not a forced
        # Gaussian fit to clipped pixels or irregular wings.
        valid &= (frame.mask[sy, sx] & (9 | 16)) == 0
        if valid.sum() < 10:
            continue
        gy, gx = np.mgrid[-2:3, -2:3]
        base = float(np.median(values[valid]))
        amplitude = max(float(np.nanmax(values)) - base, 1e-8)
        def residual(p):
            a, dx, dy, sigma, b = p
            model = b + a * np.exp(-((gx-dx)**2 + (gy-dy)**2)/(2*sigma**2))
            return ((model-values)/errors)[valid]
        if saturated:
            usable = np.isfinite(values) & ((frame.mask[sy, sx] & 9) == 0)
            weights = np.where(usable, np.maximum(values-base, 0), 0)
            norm = weights.sum()
            if norm <= 0:
                continue
            dx, dy = float((weights*gx).sum()/norm), float((weights*gy).sum()/norm)
            sigma = float(np.sqrt((weights*((gx-dx)**2+(gy-dy)**2)).sum()/(2*norm)))
            chi = None
            method = 'saturated_moment_approximate'
        else:
            fit = least_squares(residual, [amplitude, 0, 0, .5, base],
                                bounds=([0, -.9, -.9, .25, -np.inf],
                                        [np.inf, .9, .9, 1.5, np.inf]), max_nfev=80)
            if not fit.success:
                continue
            _, dx, dy, sigma, _ = fit.x
            chi = float(np.sum(fit.fun**2) / max(1, valid.sum()-5))
            method = 'gaussian'
        if np.hypot(dx, dy) > 1.0:
            continue
        # Deduplicate neighbouring peaks of a flat/saturated core.
        cx, cy = x + dx, y + dy
        if _nearby_accepted(accepted_cells, cx, cy):
            continue
        ra, dec = frame.wcs.pixel_to_world_values(cx, cy)
        if not np.isfinite([ra, dec]).all():
            continue
        flags = []
        if bits & 2: flags.append('suspect_bit_2_kept')
        if bits & 32: flags.append('star_residue')
        if saturated: flags.append('saturated_centroid_uncertain')
        if sigma < .28: flags.append('sharp_or_undersampled')
        if sigma > .9: flags.append('broad_or_blended')
        if chi is not None and chi > 5: flags.append('poor_gaussian_fit')
        uncertainty = max(cfg.centroid_floor_px, sigma / score[y, x])
        if chi is not None:
            uncertainty *= max(1, min(3, np.sqrt(chi)))
        if saturated: uncertainty = max(uncertainty, cfg.saturated_centroid_floor_px)
        local_wave = float(frame.wave[y, x]) if frame.wave is not None else None
        if local_wave is not None and not np.isfinite(local_wave):
            local_wave = None
            flags.append('local_wavelength_unavailable')
        results.append(dict(patch=frame.row['patch'], frame=int(frame.row['frame']),
            file=frame.row['file'], x=float(cx), y=float(cy), snr=float(score[y,x]),
            raw_peak_snr=float(frame.snr[y,x]), t_mid_mjd=float(frame.row['t_mid_mjd']),
            ra_deg=float(ra), dec_deg=float(dec), detector=frame.row['detector'],
            wavelength_um=local_wave, center_wavelength_um=float(frame.row['wl_um']),
            centroid_error_px=float(uncertainty), centroid_method=method,
            gaussian_sigma_px=None if saturated else float(sigma),
            moment_sigma_px=float(sigma) if saturated else None,
            fit_reduced_chi2=chi, mask_bits=bits, flags=flags))
        accepted_cells.setdefault((floor(cx), floor(cy)), []).append((cx, cy))
    frame.detections = results
    return results

