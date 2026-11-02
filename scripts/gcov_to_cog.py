#!/usr/bin/env python3
"""Shrink a NISAR L2 GCOV file (L- or S-band) to analysis-ready Cloud-Optimized GeoTIFFs.

For frequency A only (frequency B is poorly calibrated, see PLAN.md), writes one GeoTIFF per
diagonal covariance term (HHHH, HVHV, VVVV, VHVH, RHRH, RVRV: gamma-0 backscatter power, LINEAR
units), plus number of looks and a valid-pixel mask, block-averaged from the native spacing
(10 or 20 m) to --spacing (default 20 m). Averaging is done in linear power, never in dB.
--offdiag also writes the complex off-diagonal terms (quad-pol / compact-pol) as 2-band
real/imag files. The quad-pol 59 degree phase correction is NOT applied here (see PLAN.md).

The full frame is always processed; there is no clipping option on purpose.

    python scripts/gcov_to_cog.py data/raw/L/NISAR_L2_PR_GCOV_....h5 --out-dir data/work/L
"""
import argparse
import os
import sys

import h5py
import numpy as np
import rasterio
from rasterio.shutil import copy as rio_copy
from rasterio.transform import Affine

DIAGONAL = ["HHHH", "HVHV", "VVVV", "VHVH", "RHRH", "RVRV", "LHLH", "LVLV"]


def find_grid(f):
    for band in ("LSAR", "SSAR"):
        p = f"/science/{band}/GCOV/grids/frequencyA"
        if p in f:
            return band, f[p]
    sys.exit("No /science/{LSAR,SSAR}/GCOV/grids/frequencyA group: is this a GCOV file?")


def epsg_of(grid):
    proj = grid["projection"]
    for k in ("epsg_code", "epsg"):
        if k in proj.attrs:
            return int(np.ravel(proj.attrs[k])[0])
    try:
        v = int(np.ravel(proj[()])[0])
        if 1024 <= v <= 32767:
            return v
    except (TypeError, ValueError):
        pass
    sys.exit("Could not read the EPSG code from frequencyA/projection; inspect the file and update epsg_of().")


def ident(f, band):
    out = {}
    p = f"/science/{band}/identification"
    if p in f:
        for k in ("zeroDopplerStartTime", "orbitPassDirection", "trackNumber", "frameNumber",
                  "compositeReleaseId", "productVersion", "isUrgentObservation", "listOfFrequencies"):
            if k in f[p]:
                v = f[p][k][()]
                out[k] = v.decode() if isinstance(v, bytes) else str(np.ravel(v).tolist() if np.ndim(v) else v)
    return out


def block_mean(a, k):
    """Mean over k x k blocks ignoring NaN; NaN where fewer than half the samples are valid."""
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    a = a[:h, :w].reshape(h // k, k, w // k, k)
    valid = np.isfinite(a)
    n = valid.sum(axis=(1, 3))
    s = np.where(valid, a, 0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / n
    m[n < (k * k) / 2] = np.nan
    return m


def write_cog(path, arrays_fn, out_h, out_w, count, dtype, transform, crs, tags, nodata, rows_per_strip):
    tmp = path + ".tmp.tif"
    prof = dict(driver="GTiff", height=out_h, width=out_w, count=count, dtype=dtype, crs=crs, transform=transform,
                nodata=nodata, tiled=True, blockxsize=512, blockysize=512, compress="DEFLATE",
                predictor=3 if dtype == "float32" else 2, BIGTIFF="IF_SAFER")
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.update_tags(**tags)
        for r0 in range(0, out_h, rows_per_strip):
            r1 = min(r0 + rows_per_strip, out_h)
            block = arrays_fn(r0, r1)
            for b in range(count):
                dst.write(block[b], b + 1, window=((r0, r1), (0, out_w)))
    rio_copy(tmp, path, driver="COG", compress="DEFLATE", predictor=3 if dtype == "float32" else 2,
             BIGTIFF="IF_SAFER", overview_resampling="average")
    os.remove(tmp)
    print(f"  wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("h5")
    ap.add_argument("--out-dir", default="data/work")
    ap.add_argument("--spacing", type=float, default=20.0, help="output pixel spacing in metres")
    ap.add_argument("--offdiag", action="store_true", help="also export complex off-diagonal terms")
    ap.add_argument("--coords-are-corners", action="store_true",
                    help="treat x/yCoordinates as pixel corners instead of pixel centres")
    a = ap.parse_args()

    name = os.path.basename(a.h5).rsplit(".", 1)[0]
    os.makedirs(a.out_dir, exist_ok=True)
    with h5py.File(a.h5, "r") as f:
        band, g = find_grid(f)
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
        k = max(1, int(round(a.spacing / abs(dx))))
        if abs(k * abs(dx) - a.spacing) > 0.01 * a.spacing:
            print(f"  note: native spacing {abs(dx)} m does not divide {a.spacing} m; using factor {k} "
                  f"-> {k * abs(dx)} m")
        x0 = x[0] if a.coords_are_corners else x[0] - dx / 2
        y0 = y[0] if a.coords_are_corners else y[0] - dy / 2
        transform = Affine(dx * k, 0, x0, 0, dy * k, y0)
        crs = f"EPSG:{epsg_of(g)}"
        H, W = g[next(t for t in DIAGONAL if t in g)].shape
        out_h, out_w = H // k, W // k
        rows = max(1, 4096 // k)  # output rows per strip -> ~4096 input rows in memory at a time
        base_tags = dict(source_granule=name, radar_band=band, frequency="A", native_spacing_m=abs(dx),
                         block_average_factor=k, output_spacing_m=abs(dx) * k, **ident(f, band))
        terms = [t for t in DIAGONAL if t in g]
        print(f"{name}: {band} frequencyA {H}x{W} @ {abs(dx)} m, {crs}, terms {terms} -> {out_h}x{out_w} @ {abs(dx) * k} m")

        for t in terms:
            ds = g[t]

            def strip(r0, r1, ds=ds):
                a_ = ds[r0 * k:r1 * k, :out_w * k].astype("float32")
                a_[(a_ <= 0) | ~np.isfinite(a_)] = np.nan
                return block_mean(a_, k)[None]

            write_cog(os.path.join(a.out_dir, f"{name}_{t}_{int(abs(dx) * k)}m.tif"), strip, out_h, out_w, 1,
                      "float32", transform, crs, dict(base_tags, term=t, units="gamma0 power (linear)"),
                      np.nan, rows)

        if "numberOfLooks" in g:
            nl, ref = g["numberOfLooks"], g[terms[0]]

            def looks(r0, r1):
                a_ = nl[r0 * k:r1 * k, :out_w * k].astype("float32")
                v = ref[r0 * k:r1 * k, :out_w * k]
                a_[~(np.isfinite(v) & (v > 0))] = np.nan
                m = block_mean(a_, k)
                return (m * k * k)[None]  # looks add up when averaging k*k pixels

            write_cog(os.path.join(a.out_dir, f"{name}_numberOfLooks_{int(abs(dx) * k)}m.tif"), looks, out_h, out_w,
                      1, "float32", transform, crs, dict(base_tags, term="numberOfLooks"), np.nan, rows)

        if "mask" in g:
            mk = g["mask"]

            def mask(r0, r1):  # nearest-neighbour (top-left sample of each block); see product spec for codes
                return mk[r0 * k:r1 * k:k, :out_w * k:k][None].astype("uint8")

            write_cog(os.path.join(a.out_dir, f"{name}_mask_{int(abs(dx) * k)}m.tif"), mask, out_h, out_w, 1,
                      "uint8", transform, crs, dict(base_tags, term="mask (nearest)"), None, rows)

        if a.offdiag:
            for t in [t for t in g if len(t) == 4 and t.isupper() and t not in DIAGONAL and g[t].ndim == 2]:
                ds = g[t]

                def cplx(r0, r1, ds=ds):
                    c = ds[r0 * k:r1 * k, :out_w * k]
                    return np.stack([block_mean(c.real.astype("float32"), k),
                                     block_mean(c.imag.astype("float32"), k)])

                write_cog(os.path.join(a.out_dir, f"{name}_{t}_{int(abs(dx) * k)}m.tif"), cplx, out_h, out_w, 2,
                          "float32", transform, crs,
                          dict(base_tags, term=t, bands="1=real,2=imag", phase_correction_applied="no"), np.nan, rows)


if __name__ == "__main__":
    main()
