#!/usr/bin/env python3
"""Download the supporting (non-SAR) layers for both NISAR frames and align them to our 20 m grid.

No login needed. Layers:
  jrc_occurrence, jrc_seasonality  JRC Global Surface Water v1.4 (1984-2021), 30 m   -> persistent water
  worldcover                       ESA WorldCover 2021 v200, 10 m                     -> land-cover strata
  hand                             GLO-30 HAND (height above nearest drainage), 30 m -> remove hill false water
  dem                              Copernicus GLO-30 DEM, 30 m                        -> slope

    python scripts/fetch_ancillary.py                      # download tiles to data/ancillary/
    python scripts/fetch_ancillary.py --warp-to data/work/L/<granule>_HHHH_20m.tif --out-dir data/work/ancillary
"""
import argparse
import glob
import math
import os

import numpy as np
import rasterio
import requests
from rasterio.shutil import copy as rio_copy
from rasterio.warp import Resampling, reproject

BBOX = (84.4, 23.2, 88.9, 26.3)  # W, S, E, N: union of frame 98/14 and 120/76 footprints
JRC = "https://storage.googleapis.com/global-surface-water/downloads2021/{layer}/{layer}_{lon}E_{lat}Nv1_4_2021.tif"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N{lat:02d}E{lon:03d}_Map.tif"
HAND = "https://glo-30-hand.s3.us-west-2.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_HAND.tif"
DEM = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/"
       "Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif")
# layer -> (resampling to the 20 m grid, output dtype, nodata)
WARP = {"jrc_occurrence": (Resampling.average, "float32", np.nan), "jrc_seasonality": (Resampling.mode, "uint8", 255),
        "worldcover": (Resampling.mode, "uint8", 0), "hand": (Resampling.average, "float32", np.nan),
        "dem": (Resampling.bilinear, "float32", np.nan)}


def urls():
    W, S, E, N = BBOX
    out = {k: [] for k in WARP}
    for lon in range(int(W // 10 * 10), int(math.ceil(E / 10) * 10), 10):        # JRC: 10 deg, named by NW corner
        for lat in range(int(math.ceil(N / 10) * 10), int(S // 10 * 10), -10):
            for layer in ("occurrence", "seasonality"):
                out[f"jrc_{layer}"].append(JRC.format(layer=layer, lon=lon, lat=lat))
    for lat in range(int(S // 3 * 3), int(math.ceil(N / 3) * 3), 3):            # WorldCover: 3 deg, SW corner
        for lon in range(int(W // 3 * 3), int(math.ceil(E / 3) * 3), 3):
            out["worldcover"].append(WC.format(lat=lat, lon=lon))
    for lat in range(int(math.floor(S)), int(math.ceil(N))):                     # GLO-30: 1 deg, SW corner
        for lon in range(int(math.floor(W)), int(math.ceil(E))):
            out["hand"].append(HAND.format(lat=lat, lon=lon))
            out["dem"].append(DEM.format(lat=lat, lon=lon))
    return out


def download(root):
    for layer, us in urls().items():
        d = os.path.join(root, layer)
        os.makedirs(d, exist_ok=True)
        for u in us:
            dest = os.path.join(d, u.rsplit("/", 1)[1])
            if os.path.exists(dest):
                continue
            r = requests.get(u, stream=True, timeout=(30, 300))
            if r.status_code == 404:  # e.g. no tile over open water
                print(f"  missing (skipped): {u}")
                continue
            r.raise_for_status()
            with open(dest + ".part", "wb") as f:
                for chunk in r.iter_content(8 << 20):
                    f.write(chunk)
            os.replace(dest + ".part", dest)
        print(f"{layer}: {len(glob.glob(os.path.join(d, '*.tif')))} tiles in {d}")


def warp_to(root, ref, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with rasterio.open(ref) as r:
        crs, transform, shape = r.crs, r.transform, (r.height, r.width)
    for layer, (resampling, dtype, nodata) in WARP.items():
        tiles = sorted(glob.glob(os.path.join(root, layer, "*.tif")))
        if not tiles:
            print(f"{layer}: no tiles, run without --warp-to first"); continue
        dst = np.full(shape, nodata, dtype=dtype)
        for t in tiles:
            with rasterio.open(t) as src:
                reproject(rasterio.band(src, 1), dst, dst_transform=transform, dst_crs=crs, dst_nodata=nodata,
                          resampling=resampling, init_dest_nodata=False)
        out = os.path.join(out_dir, f"{layer}_20m.tif")
        prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=1, dtype=dtype, crs=crs,
                    transform=transform, nodata=nodata, tiled=True, compress="DEFLATE")
        with rasterio.open(out + ".tmp.tif", "w", **prof) as f:
            f.write(dst, 1)
        rio_copy(out + ".tmp.tif", out, driver="COG", compress="DEFLATE")
        os.remove(out + ".tmp.tif")
        valid = np.isfinite(dst) if dtype == "float32" else dst != nodata
        print(f"{layer}: -> {out} ({100 * valid.mean():.1f}% of grid covered)")
        if layer == "dem":  # slope in degrees on the projected grid
            gy, gx = np.gradient(dst.astype("float64"), abs(transform.e), transform.a)
            slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
            with rasterio.open(os.path.join(out_dir, "slope_20m.tmp.tif"), "w", **prof) as f:
                f.write(slope, 1)
            rio_copy(os.path.join(out_dir, "slope_20m.tmp.tif"), os.path.join(out_dir, "slope_20m.tif"),
                     driver="COG", compress="DEFLATE")
            os.remove(os.path.join(out_dir, "slope_20m.tmp.tif"))
            print(f"slope: -> {os.path.join(out_dir, 'slope_20m.tif')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data/ancillary")
    ap.add_argument("--warp-to", help="reference GeoTIFF whose grid (CRS, 20 m pixels, extent) the layers are aligned to")
    ap.add_argument("--out-dir", default="data/work/ancillary")
    a = ap.parse_args()
    download(a.root)
    if a.warp_to:
        warp_to(a.root, a.warp_to, a.out_dir)


if __name__ == "__main__":
    main()
