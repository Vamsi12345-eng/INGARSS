#!/usr/bin/env python3
"""Sub-pixel L-vs-S co-registration on the shared 20 m lattice, inside/outside the S-band sample-shift flag.

Phase-correlates HH dB (upsampled 20x, so 0.05 px = 1 m steps) in 10 km windows with enough contrast and
reports the median offset; also the S-L dB difference inside vs. outside inputDataExceptionMask = 64.
Results on 3 Nov 2026 are in PLAN.md (18 Oct and 12 Sep ascending: 0.00 +/- 0.05 px; 14 Sep descending:
-0.20 px in y).

    python scripts/coreg_check.py data/work/L/<L>_HHHH_20m.tif data/work/S/<S>_HHHH_20m.tif \
        data/work/S/<S>_inputDataExceptionMask_20m.tif   # descending compact-pol: pass the RHRH file
"""
import sys
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from skimage.registration import phase_cross_correlation

Lp, Sp, Ep = sys.argv[1:4]
with rasterio.open(Lp) as L, rasterio.open(Sp) as S, rasterio.open(Ep) as E:
    assert L.crs == S.crs and L.res == S.res
    off = ((S.transform.c - L.transform.c) / L.res[0], (L.transform.f - S.transform.f) / L.res[1])
    print("S origin offset in L pixels (x, y):", off, "-> on the same lattice:", all(abs(o - round(o)) < 1e-6 for o in off))
    win = from_bounds(*S.bounds, transform=L.transform)  # S footprint inside the L grid
    l = L.read(1, window=win.round_offsets().round_lengths())
    s, e = S.read(1), E.read(1)
h, w = min(l.shape[0], s.shape[0]), min(l.shape[1], s.shape[1])
l, s, e = l[:h, :w], s[:h, :w], e[:h, :w]
with np.errstate(divide="ignore", invalid="ignore"):
    ldb, sdb = 10 * np.log10(l), 10 * np.log10(s)
rows = []
n = 512
for y0 in range(0, h - n, n):
    for x0 in range(0, w - n, n):
        a, b, ee = ldb[y0:y0 + n, x0:x0 + n], sdb[y0:y0 + n, x0:x0 + n], e[y0:y0 + n, x0:x0 + n]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.mean() < 0.98 or np.nanstd(a) < 2.0:
            continue
        a = np.where(ok, a - np.nanmean(a), 0); b = np.where(ok, b - np.nanmean(b), 0)
        shift, err, _ = phase_cross_correlation(a, b, upsample_factor=20, normalization=None)
        flag = (ee == 64).mean()
        cc = np.corrcoef(a[ok], b[ok])[0, 1]
        rows.append((flag, shift[0], shift[1], cc))
r = np.array(rows).reshape(-1, 4)
print(f"{len(r)} windows of {n}x{n} px (10 km) with enough contrast")
if not len(r):
    sys.exit("no usable windows: are both files complete and on overlapping grids?")
for name, sel in (("flagged (>90% code 64)", r[:, 0] > 0.9), ("unflagged (<10% code 64)", r[:, 0] < 0.1)):
    if sel.sum():
        dy, dx, cc = r[sel, 1], r[sel, 2], r[sel, 3]
        print(f"  {name:26s} n={sel.sum():3d}  dy median {np.median(dy):+.3f} px (IQR {np.percentile(dy, 25):+.2f}..{np.percentile(dy, 75):+.2f})"
              f"  dx median {np.median(dx):+.3f} px (IQR {np.percentile(dx, 25):+.2f}..{np.percentile(dx, 75):+.2f})  r_dB median {np.median(cc):.2f}")
# radiometric difference S-L inside vs outside the flag (same date, same pass)
d = sdb - ldb
fin = np.isfinite(d)
for name, sel in (("flagged", fin & (e == 64)), ("unflagged", fin & (e == 0))):
    print(f"  S-L HH dB, {name:9s}: median {np.median(d[sel]):+.2f} dB over {sel.mean():.1%} of the grid")
