#!/usr/bin/env python3
import glob
import json
import os
import matplotlib
import numpy as np
import rasterio
from pyproj import Transformer
from scipy.ndimage import uniform_filter

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BOX = (86.3946, 25.4098, 86.6054, 25.5902)
SURFACE, MUTED = ("#fcfcfb", "#898781")
L = sorted(glob.glob("data/work/L/NISAR_L2_*_120_D_076_*_20260914T*_HHHH_20m.tif"))[0][
    : -len("_HHHH_20m.tif")
]
S = sorted(glob.glob("data/work/S/NISAR_S2_*_120_D_076_*_20260914T*_RHRH_20m.tif"))[0][
    : -len("_RHRH_20m.tif")
]


def window(path, half_x=30000, half_y=20000):
    with rasterio.open(path) as r:
        t = Transformer.from_crs("EPSG:4326", r.crs, always_xy=True)
        cx, cy = t.transform((BOX[0] + BOX[2]) / 2, (BOX[1] + BOX[3]) / 2)
        c0, r0 = ~r.transform * (cx - half_x, cy + half_y)
        c1, r1 = ~r.transform * (cx + half_x, cy - half_y)
    return ((int(r0), int(r1)), (int(c0), int(c1)))


def read(path, win, band=1):
    with rasterio.open(path) as r:
        return r.read(band, window=win).astype("float64")


def smooth(a, k=5):
    m = np.isfinite(a)
    num = uniform_filter(np.where(m, a, 0.0), k)
    den = uniform_filter(m.astype("float64"), k)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den >= 0.5, num / den, np.nan)


def stretch(a, lo=2, hi=98):
    v = a[np.isfinite(a)]
    p0, p1 = np.percentile(v, [lo, hi])
    return np.clip((a - p0) / (p1 - p0), 0, 1)


def main():
    out = {}
    wl = window(f"{L}_HHHH_20m.tif")
    hh, vv, hv, vh = (smooth(read(f"{L}_{t}_20m.tif", wl)) for t in ("HHHH", "VVVV", "HVHV", "VHVH"))
    raw = read(f"{L}_HHVV_20m.tif", wl, 1) + 1j * read(f"{L}_HHVV_20m.tif", wl, 2)
    hh_raw = read(f"{L}_HHHH_20m.tif", wl)
    with np.errstate(invalid="ignore", divide="ignore"):
        db_raw = 10 * np.log10(hh_raw)
    check = {}
    for name, sel in (("open_water_HH_below_-18dB", db_raw < -18), ("bright_HH_above_-3dB", db_raw > -3)):
        z = raw[sel & np.isfinite(raw)].sum()
        check[name] = {
            "uncorrected_deg": round(float(np.degrees(np.angle(z))), 1),
            "with_plus_59_deg": round(float(np.degrees(np.angle(z * np.exp(1j * np.deg2rad(59))))), 1),
            "with_minus_59_deg": round(float(np.degrees(np.angle(z * np.exp(-1j * np.deg2rad(59))))), 1),
        }
    out["HHVV_phase_check"] = check
    c = (smooth(raw.real) + 1j * smooth(raw.imag)) * np.exp(1j * np.deg2rad(59))
    pauli = np.dstack(
        [
            stretch(np.sqrt(np.clip(hh + vv - 2 * c.real, 0, None))),
            stretch(np.sqrt(np.clip(hv + vh, 0, None))),
            stretch(np.sqrt(np.clip(hh + vv + 2 * c.real, 0, None))),
        ]
    )
    phase = np.degrees(np.angle(c))
    with np.errstate(invalid="ignore", divide="ignore"):
        coh = np.abs(c) / np.sqrt(hh * vv)
        hh_db = 10 * np.log10(hh)
    dbl = (np.abs(phase) > 120) & (hh_db > -6) & (coh > 0.3)
    out["L_quadpol"] = dict(
        pixels=int(np.isfinite(phase).sum()),
        double_bounce_share=round(float(dbl.mean()), 4),
        median_HHVV_coherence=round(float(np.nanmedian(coh)), 3),
        phase_correction_deg=+59,
    )
    ws = window(f"{S}_RHRH_20m.tif")
    rh, rv = (smooth(read(f"{S}_RHRH_20m.tif", ws)), smooth(read(f"{S}_RVRV_20m.tif", ws)))
    x = smooth(read(f"{S}_RHRV_20m.tif", ws, 1)) + 1j * smooth(read(f"{S}_RHRV_20m.tif", ws, 2))
    s0, s1, s2, s3 = (rh + rv, rh - rv, 2 * x.real, -2 * x.imag)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.sqrt(s1**2 + s2**2 + s3**2) / s0
        sin2chi = -s3 / (m * s0)
    dark = s0 < np.nanpercentile(s0, 1)
    flip = np.nanmedian(sin2chi[dark]) > 0
    if flip:
        sin2chi = -sin2chi
    mchi = np.dstack(
        [
            stretch(np.sqrt(np.clip(m * s0 * (1 + sin2chi) / 2, 0, None))),
            stretch(np.sqrt(np.clip(s0 * (1 - m), 0, None))),
            stretch(np.sqrt(np.clip(m * s0 * (1 - sin2chi) / 2, 0, None))),
        ]
    )
    out["S_compactpol"] = dict(
        pixels=int(np.isfinite(m).sum()),
        median_m=round(float(np.nanmedian(m)), 3),
        s3_sign_flipped_to_make_water_odd_bounce=bool(flip),
    )
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))
    ax[0].imshow(np.nan_to_num(pauli))
    ax[0].set_title("L-band quad-pol, Pauli RGB\nR double bounce · G volume · B surface")
    im = ax[1].imshow(np.where(np.isfinite(phase), phase, np.nan), cmap="twilight", vmin=-180, vmax=180)
    ax[1].set_title("L-band HH−VV phase difference (deg)\nafter the +59° correction; ±180° = double bounce")
    plt.colorbar(im, ax=ax[1], fraction=0.035, pad=0.02, ticks=[-180, -90, 0, 90, 180])
    ax[2].imshow(np.nan_to_num(mchi))
    ax[2].set_title("S-band compact-pol, m-χ RGB\nR even bounce · G volume · B odd bounce")
    for a in ax:
        a.set_xticks([])
        a.set_yticks([])
    fig.text(
        0.01,
        0.01,
        "NISAR L2 GCOV, descending track 120 frame 76, 14 Sep 2026 12:50 UTC; 60 x 40 km around the reference box; 20 m, 5x5 boxcar; UTM 45N (EPSG:32645)",
        fontsize=8,
        color=MUTED,
    )
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs("docs/figures", exist_ok=True)
    fig.savefig("docs/figures/fig_polarimetry.png", dpi=150, bbox_inches="tight", facecolor=SURFACE)
    os.makedirs("docs/results", exist_ok=True)
    json.dump(out, open("docs/results/polarimetry_20260914.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
