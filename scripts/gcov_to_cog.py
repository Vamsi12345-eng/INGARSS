#!/usr/bin/env python3
"""Shrink a NISAR L2 GCOV file (L- or S-band) to analysis-ready Cloud-Optimized GeoTIFFs.

For frequency A only (frequency B is poorly calibrated, see PLAN.md), writes one GeoTIFF per
diagonal covariance term (HHHH, HVHV, VVVV, VHVH, RHRH, RVRV: gamma-0 backscatter power, LINEAR
units), plus number of looks and a valid-pixel mask, block-averaged from the native spacing
(10 or 20 m) to --spacing (default 20 m). Averaging is done in linear power, never in dB.
--offdiag also writes the complex off-diagonal terms (quad-pol / compact-pol) as 2-band
real/imag files. The quad-pol 59 degree phase correction is NOT applied here (see PLAN.md).

Samples that the GCOV mask marks invalid (0) or outside the swath (255) are dropped before
averaging; an output pixel is NaN unless at least half of its native samples are valid, and the
output mask follows the same rule. The input-data-exception mask (S-band "sample shift" flags)
is exported as the bitwise OR over each block. x/yCoordinates are pixel centres (the L-band
product says so in its pixel_coordinate_convention attribute; S-band spec 1.2.1 omits it).
Covariance terms and looks are rounded to 16 mantissa bits, the precision the L-band product
stores its covariance terms with (--keep-bits 23 turns this off).

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


def block_mean(a, k, return_count=False):
    """Mean over k x k blocks ignoring NaN; NaN where fewer than half the samples are valid."""
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    a = a[:h, :w].reshape(h // k, k, w // k, k)
    valid = np.isfinite(a)
    n = valid.sum(axis=(1, 3))
    s = np.where(valid, a, 0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        m = (s / n).astype("float32")
    m[n < (k * k) / 2] = np.nan
    return (m, n) if return_count else m


def valid_samples(mk):
    """GCOV mask codes (product spec, checked on a real file 3 Nov 2026): 1..254 = valid sample (value is the
    sub-swath number), 0 = invalid (partially focused or invalid radar samples), 255 = outside the acquisition."""
    return (mk > 0) & (mk < 255)


def round_mantissa(a, keep):
    """Round float32 values to `keep` explicit mantissa bits (round half to even); NaN/inf unchanged.
    NISAR GCOV covariance terms are stored with 16 mantissa bits, so keep=16 stores the 20 m averages at the
    product's own precision (relative error <= 2**-17, about 0.00003 dB) and makes them compress about 20% better."""
    if keep >= 23:
        return a
    a = np.ascontiguousarray(a, dtype="float32")
    drop = 23 - keep
    u = a.view(np.uint32)
    bias = np.uint32((1 << (drop - 1)) - 1) + ((u >> np.uint32(drop)) & np.uint32(1))
    r = ((u + bias) & ~np.uint32((1 << drop) - 1)).view(np.float32)
    return np.where(np.isfinite(a), r, a)


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
                    help="treat x/yCoordinates as pixel corners instead of pixel centres (the product declares "
                         "pixel_coordinate_convention=center, so this is off by default)")
    ap.add_argument("--keep-bits", type=int, default=16,
                    help="float32 mantissa bits kept in covariance terms and looks (default 16 = the product's "
                         "own precision for covariance terms; 23 = no rounding)")
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
        mk = g["mask"] if "mask" in g else None
        keep = a.keep_bits
        base_tags = dict(source_granule=name, radar_band=band, frequency="A", native_spacing_m=abs(dx),
                         block_average_factor=k, output_spacing_m=abs(dx) * k,
                         masked_samples="GCOV mask 0 and 255 excluded before averaging" if mk is not None
                         else "no GCOV mask in file", **ident(f, band))
        terms = [t for t in DIAGONAL if t in g]
        print(f"{name}: {band} frequencyA {H}x{W} @ {abs(dx)} m, {crs}, terms {terms} -> {out_h}x{out_w} @ {abs(dx) * k} m")

        def bad_samples(r0, r1):  # True where the GCOV mask says a native sample is invalid or outside the swath
            return ~valid_samples(mk[r0 * k:r1 * k, :out_w * k]) if mk is not None else False

        for t in terms:
            ds = g[t]

            def strip(r0, r1, ds=ds):
                a_ = ds[r0 * k:r1 * k, :out_w * k].astype("float32")
                a_[(a_ <= 0) | ~np.isfinite(a_) | bad_samples(r0, r1)] = np.nan
                return round_mantissa(block_mean(a_, k), keep)[None]

            write_cog(os.path.join(a.out_dir, f"{name}_{t}_{int(abs(dx) * k)}m.tif"), strip, out_h, out_w, 1,
                      "float32", transform, crs, dict(base_tags, term=t, units="gamma0 power (linear)",
                                                      mantissa_bits_kept=min(keep, 23)), np.nan, rows)

        if "numberOfLooks" in g:
            nl, ref = g["numberOfLooks"], g[terms[0]]

            def looks(r0, r1):
                a_ = nl[r0 * k:r1 * k, :out_w * k].astype("float32")
                v = ref[r0 * k:r1 * k, :out_w * k]
                a_[~(np.isfinite(v) & (v > 0)) | bad_samples(r0, r1)] = np.nan
                m, n = block_mean(a_, k, return_count=True)
                return round_mantissa(m * n, keep)[None]  # looks add up over the valid samples in each output pixel

            write_cog(os.path.join(a.out_dir, f"{name}_numberOfLooks_{int(abs(dx) * k)}m.tif"), looks, out_h, out_w,
                      1, "float32", transform, crs, dict(base_tags, term="numberOfLooks",
                                                         mantissa_bits_kept=min(keep, 23)), np.nan, rows)

        if mk is not None:
            def mask(r0, r1):  # same validity rule as the averaged terms
                m = mk[r0 * k:r1 * k, :out_w * k]
                h_, w_ = m.shape[0] // k, m.shape[1] // k
                b = m[:h_ * k, :w_ * k].reshape(h_, k, w_, k)
                v = valid_samples(b)
                sub = np.where(v, b, 0).max(axis=(1, 3))  # sub-swath number among the valid samples
                outside = (b == 255).all(axis=(1, 3))
                return np.where(v.sum(axis=(1, 3)) >= (k * k) / 2, sub, np.where(outside, 255, 0))[None].astype("uint8")

            write_cog(os.path.join(a.out_dir, f"{name}_mask_{int(abs(dx) * k)}m.tif"), mask, out_h, out_w, 1,
                      "uint8", transform, crs,
                      dict(base_tags, term="mask: 1..254 valid (sub-swath number; at least half of the averaged "
                                           "samples valid), 0 invalid, 255 outside the acquisition"), None, rows)

        if "inputDataExceptionMask" in g:  # S-band: code 64 = "NISAR SSAR sample shift" (36% of 18 Oct 2026 swath)
            ex = g["inputDataExceptionMask"]

            def exc(r0, r1):  # bitwise OR of the exception codes of the native samples in each block
                e = ex[r0 * k:r1 * k, :out_w * k]
                h_, w_ = e.shape[0] // k, e.shape[1] // k
                b = e[:h_ * k, :w_ * k].reshape(h_, k, w_, k)
                inside = b != 255
                o = np.bitwise_or.reduce(np.where(inside, b, 0), axis=(1, 3))
                return np.where(inside.any(axis=(1, 3)), o, 255)[None].astype("uint8")

            write_cog(os.path.join(a.out_dir, f"{name}_inputDataExceptionMask_{int(abs(dx) * k)}m.tif"), exc, out_h,
                      out_w, 1, "uint8", transform, crs,
                      dict(base_tags, term="inputDataExceptionMask: bitwise OR over each block's samples "
                                           "(0 no anomaly, 64 S-band sample shift), 255 outside"), None, rows)

        if a.offdiag:
            for t in [t for t in g if len(t) == 4 and t.isupper() and t not in DIAGONAL
                      and isinstance(g[t], h5py.Dataset) and g[t].ndim == 2]:
                ds = g[t]

                def cplx(r0, r1, ds=ds):
                    c = ds[r0 * k:r1 * k, :out_w * k]
                    re, im = c.real.astype("float32"), c.imag.astype("float32")
                    bad = bad_samples(r0, r1) | ~np.isfinite(re) | ~np.isfinite(im)
                    re[bad] = np.nan
                    im[bad] = np.nan
                    return np.stack([round_mantissa(block_mean(re, k), keep), round_mantissa(block_mean(im, k), keep)])

                write_cog(os.path.join(a.out_dir, f"{name}_{t}_{int(abs(dx) * k)}m.tif"), cplx, out_h, out_w, 2,
                          "float32", transform, crs,
                          dict(base_tags, term=t, bands="1=real,2=imag", phase_correction_applied="no",
                               mantissa_bits_kept=min(keep, 23)), np.nan, rows)


if __name__ == "__main__":
    main()
