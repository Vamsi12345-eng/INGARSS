#!/usr/bin/env python3
import argparse
import json
import os
import numpy as np
import rasterio

PIX_KM2 = 0.0004
WORLDCOVER = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "cropland",
    50: "built-up",
    60: "bare/sparse",
    80: "permanent water",
    90: "herbaceous wetland",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dates", nargs=2, required=True)
    ap.add_argument("--sets", nargs="+", default=["L", "S", "LS", "L4x"])
    ap.add_argument("--maps", default="data/work/maps")
    ap.add_argument("--ancillary", default="data/work/ancillary")
    ap.add_argument("--out-dir", default="docs/results")
    a = ap.parse_args()
    d1, d2 = (x.replace("-", "") for x in a.dates)
    os.makedirs(a.out_dir, exist_ok=True)
    anc = {}
    for k in ("worldcover", "hand", "jrc_occurrence"):
        p = f"{a.ancillary}/{k}_20m.tif"
        if os.path.exists(p):
            with rasterio.open(p) as r:
                anc[k] = r.read(1)
    out = dict(dates=a.dates, sets={})
    for s in a.sets:
        p1, p2 = (f"{a.maps}/water_{d1}_{s}_20m.tif", f"{a.maps}/water_{d2}_{s}_20m.tif")
        if not (os.path.exists(p1) and os.path.exists(p2)):
            continue
        with rasterio.open(p1) as r1, rasterio.open(p2) as r2:
            P1, W1, P2, W2 = (r1.read(1), r1.read(2), r2.read(1), r2.read(2))
            prof = r1.profile
        ok = (W1 != 255) & (W2 != 255)
        w1, w2 = (W1 == 1, W2 == 1)
        cls = np.full(W1.shape, 255, "uint8")
        cls[ok & ~w1 & ~w2] = 0
        cls[ok & w1 & w2] = 1
        cls[ok & ~w1 & w2] = 2
        cls[ok & w1 & ~w2] = 3
        f1, f2 = (P1.astype("float32") / 100, P2.astype("float32") / 100)
        pg = np.where(ok, np.round(100 * f2 * (1 - f1)), 255).astype("uint8")
        pl = np.where(ok, np.round(100 * f1 * (1 - f2)), 255).astype("uint8")
        prof.update(
            count=3, dtype="uint8", nodata=255, compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512
        )
        path = f"{a.maps}/change_{d1}_{d2}_{s}_20m.tif"
        with rasterio.open(path, "w", **prof) as f:
            f.write(cls, 1)
            f.write(pg, 2)
            f.write(pl, 3)
            f.update_tags(
                dates=" -> ".join(a.dates),
                feature_set=s,
                band1="0 stable land, 1 stable water, 2 new water, 3 water loss, 255 no data",
                band2="P(gain) percent = P2(1-P1)",
                band3="P(loss) percent = P1(1-P2)",
            )
        row = {
            name: round(float((cls == c).sum()) * PIX_KM2, 1)
            for c, name in (
                (0, "stable_land_km2"),
                (1, "stable_water_km2"),
                (2, "new_water_km2"),
                (3, "water_loss_km2"),
            )
        }
        row["compared_km2"] = round(float(ok.sum()) * PIX_KM2, 1)
        row["confident_new_water_km2"] = round(float(((pg >= 50) & (pg != 255)).sum()) * PIX_KM2, 1)
        new = cls == 2
        if "jrc_occurrence" in anc:
            jrc = anc["jrc_occurrence"]
            row["new_water_outside_persistent_km2"] = round(float((new & ~(jrc >= 75)).sum()) * PIX_KM2, 1)
        if "worldcover" in anc:
            wc = anc["worldcover"]
            row["new_water_by_worldcover_km2"] = {
                name: round(float((new & (wc == c)).sum()) * PIX_KM2, 1)
                for c, name in WORLDCOVER.items()
                if (new & (wc == c)).any()
            }
        if "hand" in anc:
            hand = anc["hand"]
            row["new_water_by_hand_km2"] = {
                f"{lo}-{hi} m": round(float((new & (hand >= lo) & (hand < hi)).sum()) * PIX_KM2, 1)
                for lo, hi in ((0, 1), (1, 3), (3, 10), (10, 1000))
            }
        out["sets"][s] = row
        print(
            f"  {s:4s} stable water {row['stable_water_km2']:8.0f}  new {row['new_water_km2']:8.0f}  lost {row['water_loss_km2']:8.0f} km2  (compared {row['compared_km2']:.0f} km2) -> {path}",
            flush=True,
        )
    path = os.path.join(a.out_dir, f"change_{d1}_{d2}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
