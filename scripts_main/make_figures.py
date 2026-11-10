#!/usr/bin/env python3
import argparse
import glob
import json
import os
import matplotlib
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch, Rectangle
from pyproj import Transformer

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE, INK, INK2, MUTED, GRID, AXIS = ("#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7")
SERIES = {
    "L": "#2a78d6",
    "S": "#eb6834",
    "LS": "#1baf7a",
    "L4x": "#eda100",
    "AND": "#e87ba4",
    "OR": "#008300",
}
LABEL = {
    "L": "L-band only",
    "S": "S-band only",
    "LS": "L+S (Bayesian)",
    "L4x": "L, 4x looks (control)",
    "AND": "L AND S",
    "OR": "L OR S",
}
LAND, WATER = ("#e1e0d9", "#2a78d6")
CHANGE = ["#e1e0d9", "#2a78d6", "#eb6834", "#1baf7a"]
BOX = (86.3946, 25.4098, 86.6054, 25.5902)
SOURCE = (
    "NISAR L2 GCOV (L: NASA/ASF, S: ISRO/Bhoonidhi), ascending track 98 frame 14; UTM 45N (EPSG:32645), 20 m"
)
DATES = {"20260620": "20 Jun", "20260714": "14 Jul", "20260912": "12 Sep", "20261018": "18 Oct"}
UNRELIABLE = {"20260620"}
plt.rcParams.update(
    {
        "font.size": 9,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK2,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
    }
)


def grid_info(path):
    with rasterio.open(path) as r:
        return (r.transform, r.crs, (r.height, r.width))


def box_window(transform, crs, half_x=30000, half_y=20000):
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx, cy = t.transform((BOX[0] + BOX[2]) / 2, (BOX[1] + BOX[3]) / 2)
    c0, r0 = ~transform * (cx - half_x, cy + half_y)
    c1, r1 = ~transform * (cx + half_x, cy - half_y)
    bx0, by0 = ~transform * t.transform(BOX[0], BOX[3])
    bx1, by1 = ~transform * t.transform(BOX[2], BOX[1])
    return ((int(r0), int(r1), int(c0), int(c1)), (bx0, by0, bx1, by1))


def read_band(path, band, win=None, step=1):
    with rasterio.open(path) as r:
        if win is None:
            return r.read(
                band,
                out_shape=(r.height // step, r.width // step),
                resampling=rasterio.enums.Resampling.nearest,
            )
        r0, r1, c0, c1 = win
        a = r.read(band, window=((r0, r1), (c0, c1)))
        return a[::step, ::step]


def water_rgb_index(w):
    out = np.full(w.shape, 0, "uint8")
    out[w == 0] = 1
    out[w == 1] = 2
    return out


def note(fig, text):
    fig.text(0.01, 0.005, text, fontsize=7, color=MUTED, ha="left", va="bottom")


def fig_water_zoom(maps, out):
    dates = [
        d for d in ("20260714", "20260912", "20261018") if os.path.exists(f"{maps}/water_{d}_LS_20m.tif")
    ]
    if not dates:
        return
    transform, crs, _ = grid_info(f"{maps}/water_{dates[0]}_LS_20m.tif")
    win, (bx0, by0, bx1, by1) = box_window(transform, crs)
    cmap = ListedColormap([SURFACE, LAND, WATER])
    fig, axes = plt.subplots(len(dates), 3, figsize=(11, 2.55 * len(dates) + 0.6), squeeze=False)
    for i, d in enumerate(dates):
        for j, s in enumerate(("L", "S", "LS")):
            ax = axes[i, j]
            w = read_band(f"{maps}/water_{d}_{s}_20m.tif", 2, win, step=2)
            ax.imshow(water_rgb_index(w), cmap=cmap, vmin=0, vmax=2, interpolation="nearest")
            ax.add_patch(
                Rectangle(
                    ((bx0 - win[2]) / 2, (by0 - win[0]) / 2),
                    (bx1 - bx0) / 2,
                    (by1 - by0) / 2,
                    fill=False,
                    ec=INK,
                    lw=0.8,
                    ls="--",
                )
            )
            ax.set_xticks([])
            ax.set_yticks([])
            if i == 0:
                ax.set_title(LABEL[s])
            if j == 0:
                ax.set_ylabel(f"{DATES[d]} 2026", fontsize=10, color=INK)
    fig.legend(
        handles=[
            Patch(fc=WATER, label="water"),
            Patch(fc=LAND, label="land"),
            Patch(fc="none", ec=INK, ls="--", label="20 km reference box"),
        ],
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.0),
    )
    fig.suptitle(
        "Surface water around the reference box (60 x 40 km, centre 25.5N 86.5E)",
        y=1.035,
        fontsize=11,
        fontweight="bold",
    )
    note(fig, SOURCE + "; shown at 40 m. Same algorithm and training pixels for every column.")
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_change(maps, out):
    pairs = [
        (p, n)
        for p, n in (
            (("20260714", "20260912"), "gain: 14 Jul -> 12 Sep"),
            (("20260912", "20261018"), "loss: 12 Sep -> 18 Oct"),
        )
        if os.path.exists(f"{maps}/change_{p[0]}_{p[1]}_LS_20m.tif")
    ]
    if not pairs:
        return
    cmap = ListedColormap([SURFACE] + CHANGE)
    fig, axes = plt.subplots(2, len(pairs), figsize=(5.6 * len(pairs), 10.4), squeeze=False)
    for j, ((d1, d2), name) in enumerate(pairs):
        path = f"{maps}/change_{d1}_{d2}_LS_20m.tif"
        transform, crs, _ = grid_info(path)
        win, (bx0, by0, bx1, by1) = box_window(transform, crs)
        for i, (w, step) in enumerate(((None, 4), (win, 2))):
            c = read_band(path, 1, w, step)
            idx = np.where(c == 255, 0, c.astype("int16") + 1)
            ax = axes[i, j]
            ax.imshow(idx, cmap=cmap, vmin=0, vmax=4, interpolation="nearest")
            ax.set_xticks([])
            ax.set_yticks([])
            if i == 0:
                ax.set_title(f"L+S change, {name}")
                r0, r1, c0, c1 = win
                ax.add_patch(
                    Rectangle((c0 / 4, r0 / 4), (c1 - c0) / 4, (r1 - r0) / 4, fill=False, ec=INK, lw=0.8)
                )
            else:
                ax.set_title("zoom: 60 x 40 km around the reference box", fontweight="normal", fontsize=9)
                ax.add_patch(
                    Rectangle(
                        ((bx0 - win[2]) / 2, (by0 - win[0]) / 2),
                        (bx1 - bx0) / 2,
                        (by1 - by0) / 2,
                        fill=False,
                        ec=INK,
                        lw=0.8,
                        ls="--",
                    )
                )
    fig.legend(
        handles=[
            Patch(fc=CHANGE[1], label="stable water"),
            Patch(fc=CHANGE[2], label="new water"),
            Patch(fc=CHANGE[3], label="water loss"),
            Patch(fc=CHANGE[0], label="stable land"),
        ],
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 1.0),
    )
    note(fig, SOURCE + "; full frame shown at 80 m, zoom at 40 m.")
    fig.tight_layout(rect=(0, 0.02, 1, 0.975))
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_accuracy(results, out):
    vals = {
        d: json.load(open(p))
        for d, p in (
            (os.path.basename(p)[11:19], p) for p in sorted(glob.glob(f"{results}/validation_*.json"))
        )
    }
    if not vals:
        return
    order = [s for s in ("L", "S", "LS", "L4x", "AND", "OR") if any((s in v["sets"] for v in vals.values()))]
    fig, axes = plt.subplots(1, len(vals) + 1, figsize=(4.2 * (len(vals) + 1), 3.6), squeeze=False)
    for k, (d, v) in enumerate(sorted(vals.items(), reverse=True)):
        ax = axes[0, k]
        for i, s in enumerate(order[::-1]):
            if s not in v["sets"]:
                continue
            f1, (lo, hi) = (v["sets"][s]["F1"], v["sets"][s]["F1_CI95"])
            ax.plot([lo, hi], [i, i], color=SERIES[s], lw=2, solid_capstyle="round")
            ax.plot(f1, i, "o", ms=8, color=SERIES[s], mec=SURFACE, mew=2)
            ax.text(hi + 0.006, i, f"{f1:.3f}", va="center", fontsize=8, color=INK2)
        ax.set_yticks(range(len(order)), [LABEL[s] for s in order[::-1]])
        ax.set_xlabel("F1 for water (95% CI, 5 km block bootstrap)")
        ax.set_title(f"vs Sentinel-2, NISAR {DATES.get(d, d)}")
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        lo_all = min((v["sets"][s]["F1_CI95"][0] for s in order if s in v["sets"]))
        hi_all = max((v["sets"][s]["F1_CI95"][1] for s in order if s in v["sets"]))
        ax.set_xlim(lo_all - 0.02, hi_all + 0.05)
    ax = axes[0, -1]
    pairs = ["LS-L", "LS-S", "LS-L4x", "LS-AND", "LS-OR"]
    rows = [(d, p) for d in sorted(vals, reverse=True) for p in pairs if p in vals[d]["differences"]]
    for i, (d, p) in enumerate(rows[::-1]):
        dd = vals[d]["differences"][p]
        col = SERIES[p.split("-")[1]]
        ax.plot(dd["CI95"], [i, i], color=col, lw=2, solid_capstyle="round")
        ax.plot(dd["dF1"], i, "o" if d == "20261018" else "s", ms=7, color=col, mec=SURFACE, mew=2)
        ax.text(dd["CI95"][1] + 0.003, i, f"{dd['dF1']:+.3f}", va="center", fontsize=8, color=INK2)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(
        range(len(rows)),
        [f"L+S minus {LABEL[p.split('-')[1]].split(' (')[0]}  ({DATES.get(d, d)})" for d, p in rows[::-1]],
        fontsize=8,
    )
    ax.set_xlabel("difference in F1 (95% CI)")
    ax.set_title("Does fusion beat the alternatives?")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    note(
        fig,
        "Reference: Sentinel-2 L2A MNDWI > 0, clouds masked (SCL). Same pixels for every method. Positive = L+S better.",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_area(maps, results, out):
    summ = {
        os.path.basename(p)[6:14]: json.load(open(p))
        for p in sorted(glob.glob(f"{maps}/water_*_summary.json"))
    }
    if not summ:
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    import datetime as dt

    for s in ("L", "S", "LS"):
        pts = [
            (dt.datetime.strptime(d, "%Y%m%d"), v["feature_sets"][s]["water_km2"])
            for d, v in sorted(summ.items())
            if s in v["feature_sets"] and d not in UNRELIABLE
        ]
        if not pts:
            continue
        x, y = zip(*pts)
        ax.plot(x, y, "-", color=SERIES[s], lw=2)
        ax.plot(x, y, "o", ms=8, color=SERIES[s], mec=SURFACE, mew=2)
        ax.text(x[0] - dt.timedelta(days=4), y[0], LABEL[s], va="center", ha="right", fontsize=8, color=INK2)
    for p in sorted(glob.glob(f"{results}/validation_*.json")):
        v = json.load(open(p))
        if "LS" in v["sets"]:
            d = dt.datetime.strptime(v["date"], "%Y-%m-%d")
            lo, hi = v["sets"]["LS"]["adjusted_water_km2_CI95"]
            ax.plot([d, d], [lo, hi], color=INK2, lw=1.2)
            ax.plot(d, v["sets"]["LS"]["adjusted_water_km2"], "_", ms=12, color=INK2, mew=1.5)
    ax.set_ylabel("mapped water area (km2)")
    ax.set_title("Water area over the frame (domain where L and S overlap)")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    import matplotlib.dates as mdates

    ax.set_xlim(dt.datetime(2026, 6, 10), dt.datetime(2026, 10, 31))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    note(
        fig,
        "Black bars: L+S error-adjusted area with 95% CI (Olofsson 2014) on dates with a Sentinel-2 reference. 20 Jun (L only) left out: dry pre-monsoon fields mapped as water.",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_landcover(results, out):
    p = f"{results}/validation_20261018.json"
    if not os.path.exists(p):
        return
    v = json.load(open(p))
    if "by_worldcover" not in v:
        return
    rows = sorted(v["by_worldcover"].items(), key=lambda kv: -kv[1]["validated_km2"])
    rows = [(k, r) for k, r in rows if r["reference_water_share"] > 0.002][:7]
    fig, ax = plt.subplots(figsize=(6.6, 0.42 * len(rows) + 1.2))
    for i, (k, r) in enumerate(rows[::-1]):
        xs = [r[s] for s in ("L", "S", "LS")]
        ax.plot([min(xs), max(xs)], [i, i], color=GRID, lw=2)
        for s, off in (("L", -0.12), ("S", 0.0), ("LS", 0.12)):
            ax.plot(
                r[s],
                i + off,
                "o",
                ms=7,
                color=SERIES[s],
                mec=SURFACE,
                mew=1.5,
                label=LABEL[s] if i == 0 else None,
            )
        ax.text(
            1.005,
            i,
            f"{r['validated_km2']:.0f} km2, {100 * r['reference_water_share']:.1f}% water",
            va="center",
            fontsize=7.5,
            color=MUTED,
            transform=ax.get_yaxis_transform(),
        )
    ax.set_yticks(range(len(rows)), [k for k, _ in rows[::-1]])
    ax.set_xlabel("F1 for water vs Sentinel-2, 18 Oct")
    ax.set_title("Where does fusion help? F1 by ESA WorldCover class")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="lower left", frameon=False, fontsize=8, bbox_to_anchor=(0, 1.08), ncol=3)
    fig.tight_layout()
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maps", default="data/work/maps")
    ap.add_argument("--results", default="docs/results")
    ap.add_argument("--out-dir", default="docs/figures")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for name, fn, args in (
        ("fig_water_zoom.png", fig_water_zoom, (a.maps,)),
        ("fig_change_LS.png", fig_change, (a.maps,)),
        ("fig_accuracy.png", fig_accuracy, (a.results,)),
        ("fig_water_area.png", fig_area, (a.maps, a.results)),
        ("fig_by_landcover.png", fig_landcover, (a.results,)),
    ):
        out = os.path.join(a.out_dir, name)
        fn(*args, out)
        print(("wrote " if os.path.exists(out) else "skipped ") + out, flush=True)


if __name__ == "__main__":
    main()
