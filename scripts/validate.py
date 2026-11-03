#!/usr/bin/env python3
"""Validate NISAR water maps (L, S, L+S, L4x, AND, OR) against the Sentinel-2 MNDWI reference.

Wall-to-wall comparison on every pixel where the reference is clear and all maps are defined (the same
pixels for every feature set). Reports per feature set: overall accuracy, precision (user's accuracy for
water), recall (producer's accuracy), F1, IoU, mapped and error-adjusted water area (Olofsson et al. 2014,
using the reference pixels as the sample). Uncertainty: 95% CIs from a spatial block bootstrap
(5 km blocks, 1000 resamples), for F1 and for differences in F1 (dF1); McNemar tests (Foody 2004) on a
systematic 500 m subsample to limit spatial autocorrelation. Optional breakdown by ESA WorldCover class
and HAND bin when data/work/ancillary has them.

    python scripts/validate.py --date 2026-10-18 --ref data/work/ref/s2_water_20261018_20m.tif
"""
import argparse
import glob
import json
import os

import numpy as np
import rasterio
from scipy.stats import chi2

SETS = ["L", "S", "LS", "L4x", "AND", "OR"]
PAIRS = [("LS", "L"), ("LS", "S"), ("LS", "L4x"), ("S", "L"), ("LS", "OR"), ("LS", "AND")]
WORLDCOVER = {10: "tree", 20: "shrub", 30: "grass", 40: "cropland", 50: "built-up", 60: "bare/sparse",
              80: "permanent water", 90: "herbaceous wetland", 95: "mangrove", 100: "moss"}
PIX_KM2 = 0.0004
B = 256  # bootstrap block size in pixels (5.12 km)


def metrics(tp, fp, fn, tn):
    tp, fp, fn, tn = (np.asarray(v, dtype="float64") for v in (tp, fp, fn, tn))
    with np.errstate(invalid="ignore", divide="ignore"):
        prec, rec = tp / (tp + fp), tp / (tp + fn)
        return dict(OA=(tp + tn) / (tp + fp + fn + tn), precision=prec, recall=rec,
                    F1=2 * tp / (2 * tp + fp + fn), IoU=tp / (tp + fp + fn))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--maps", default="data/work/maps")
    ap.add_argument("--ancillary", default="data/work/ancillary")
    ap.add_argument("--out-dir", default="docs/results")
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args()
    d = a.date.replace("-", "")
    os.makedirs(a.out_dir, exist_ok=True)
    sets = [s for s in SETS if os.path.exists(f"{a.maps}/water_{d}_{s}_20m.tif")]
    with rasterio.open(a.ref) as r:
        ref = r.read(1)
        ref_tags = r.tags()
    maps = {}
    for s in sets:
        with rasterio.open(f"{a.maps}/water_{d}_{s}_20m.tif") as r:
            maps[s] = r.read(2)
    domain = np.ones(ref.shape, bool)
    for m in maps.values():
        domain &= m != 255
    dom_km2 = float(domain.sum()) * PIX_KM2
    valid = domain & (ref != 255)
    truth = ref == 1
    H, W = ref.shape
    nbr, nbc = H // B, W // B
    crop = (slice(0, nbr * B), slice(0, nbc * B))

    def block_sum(x):
        return x[crop].reshape(nbr, B, nbc, B).sum(axis=(1, 3)).ravel()

    counts, mapped_frac = {}, {}
    for s in sets:
        w = maps[s] == 1
        counts[s] = np.stack([block_sum(w & truth & valid), block_sum(w & ~truth & valid),
                              block_sum(~w & truth & valid), block_sum(~w & ~truth & valid)], axis=1)
        mapped_frac[s] = float((w & domain).sum()) / max(float(domain.sum()), 1)
    nblocks = counts[sets[0]].shape[0]
    has = counts[sets[0]].sum(axis=1) > 0
    idx_blocks = np.flatnonzero(has)
    rng = np.random.default_rng(0)
    boot = rng.choice(idx_blocks, size=(a.n_boot, idx_blocks.size), replace=True)

    out = dict(date=a.date, reference=os.path.basename(a.ref), reference_tiles=ref_tags.get("tiles", ""),
               domain_km2=round(dom_km2, 1), validated_km2=round(float(valid.sum()) * PIX_KM2, 1),
               reference_water_share=round(float(truth[valid].mean()), 4), blocks=int(idx_blocks.size),
               sets={}, differences={}, mcnemar={})
    f1_boot = {}
    for s in sets:
        tp, fp, fn, tn = counts[s].sum(axis=0)
        m = metrics(tp, fp, fn, tn)
        bs = counts[s][boot].sum(axis=1)  # (n_boot, 4)
        mb = metrics(bs[:, 0], bs[:, 1], bs[:, 2], bs[:, 3])
        f1_boot[s] = mb["F1"]
        # Olofsson error-adjusted water area over the whole domain (map strata = water / land)
        Ww = mapped_frac[s]
        p_w_given_mw = mb["precision"]
        p_w_given_ml = bs[:, 2] / np.maximum(bs[:, 2] + bs[:, 3], 1)
        adj = dom_km2 * (Ww * p_w_given_mw + (1 - Ww) * p_w_given_ml)
        adj_point = dom_km2 * (Ww * m["precision"] + (1 - Ww) * fn / max(fn + tn, 1))
        out["sets"][s] = {k: round(float(v), 4) for k, v in m.items()} | {
            "F1_CI95": [round(float(np.percentile(mb["F1"], 2.5)), 4), round(float(np.percentile(mb["F1"], 97.5)), 4)],
            "TP_FP_FN_TN": [int(tp), int(fp), int(fn), int(tn)],
            "mapped_water_km2": round(Ww * dom_km2, 1),
            "adjusted_water_km2": round(float(adj_point), 1),
            "adjusted_water_km2_CI95": [round(float(np.percentile(adj, 2.5)), 1), round(float(np.percentile(adj, 97.5)), 1)]}
        print(f"  {s:4s} F1 {m['F1']:.3f} [{np.percentile(mb['F1'], 2.5):.3f}, {np.percentile(mb['F1'], 97.5):.3f}]"
              f"  P {m['precision']:.3f}  R {m['recall']:.3f}  IoU {m['IoU']:.3f}  OA {m['OA']:.4f}"
              f"  mapped {Ww * dom_km2:8.0f} km2, adjusted {adj_point:8.0f} km2", flush=True)
    sub = (slice(0, None, 25), slice(0, None, 25))  # 500 m systematic subsample for McNemar
    vs, ts = valid[sub], truth[sub]
    for x, y in PAIRS:
        if x in sets and y in sets:
            dd = f1_boot[x] - f1_boot[y]
            d0 = out["sets"][x]["F1"] - out["sets"][y]["F1"]
            out["differences"][f"{x}-{y}"] = dict(dF1=round(d0, 4), CI95=[round(float(np.percentile(dd, 2.5)), 4),
                                                                         round(float(np.percentile(dd, 97.5)), 4)],
                                                  share_of_resamples_above_0=round(float((dd > 0).mean()), 3))
            cx, cy = (maps[x][sub] == 1) == ts, (maps[y][sub] == 1) == ts
            b, c = int((cx & ~cy & vs).sum()), int((~cx & cy & vs).sum())
            stat = (abs(b - c) - 1) ** 2 / (b + c) if b + c else 0.0
            out["mcnemar"][f"{x}-{y}"] = dict(only_first_correct=b, only_second_correct=c, chi2=round(stat, 2),
                                              p=float(f"{chi2.sf(stat, 1):.3g}"), n=int(vs.sum()))
            print(f"  dF1 {x}-{y}: {d0:+.4f} [{np.percentile(dd, 2.5):+.4f}, {np.percentile(dd, 97.5):+.4f}]"
                  f"  McNemar b={b} c={c} p={chi2.sf(stat, 1):.2g}", flush=True)
    # breakdowns by land cover and HAND
    wc_p, hand_p = f"{a.ancillary}/worldcover_20m.tif", f"{a.ancillary}/hand_20m.tif"
    if os.path.exists(wc_p):
        with rasterio.open(wc_p) as r:
            wc = r.read(1)
        out["by_worldcover"] = {}
        for code, name in WORLDCOVER.items():
            sel = valid & (wc == code)
            if sel.sum() < 10000:
                continue
            row = {"validated_km2": round(float(sel.sum()) * PIX_KM2, 1), "reference_water_share": round(float(truth[sel].mean()), 4)}
            for s in sets:
                w = maps[s] == 1
                row[s] = round(float(metrics((w & truth & sel).sum(), (w & ~truth & sel).sum(),
                                             (~w & truth & sel).sum(), (~w & ~truth & sel).sum())["F1"]), 4)
            out["by_worldcover"][name] = row
    if os.path.exists(hand_p):
        with rasterio.open(hand_p) as r:
            hand = r.read(1)
        out["by_hand"] = {}
        for lo, hi in ((0, 1), (1, 3), (3, 10), (10, 1e9)):
            sel = valid & (hand >= lo) & (hand < hi)
            if sel.sum() < 10000:
                continue
            row = {"validated_km2": round(float(sel.sum()) * PIX_KM2, 1), "reference_water_share": round(float(truth[sel].mean()), 4)}
            for s in sets:
                w = maps[s] == 1
                row[s] = round(float(metrics((w & truth & sel).sum(), (w & ~truth & sel).sum(),
                                             (~w & truth & sel).sum(), (~w & ~truth & sel).sum())["F1"]), 4)
            out["by_hand"][f"{lo}-{hi if hi < 1e9 else 'inf'} m"] = row
    path = os.path.join(a.out_dir, f"validation_{d}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"  -> {path}", flush=True)


if __name__ == "__main__":
    main()
