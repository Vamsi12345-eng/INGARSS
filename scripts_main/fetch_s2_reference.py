#!/usr/bin/env python3
import argparse
import json
import os
import urllib.request
import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import binary_dilation

STAC = "https://earth-search.aws.element84.com/v1/search"
CLOUDY_SCL = (3, 8, 9, 10)
BAD_SCL = (0, 1, 11)


def search(date, bbox):
    body = {
        "collections": ["sentinel-2-l2a"],
        "datetime": f"{date}T00:00:00Z/{date}T23:59:59Z",
        "bbox": list(bbox),
        "limit": 100,
    }
    req = urllib.request.Request(
        STAC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["features"]


def reflectance(asset, offset_applied, shape=None):
    rb = (asset.get("raster:bands") or [{}])[0]
    with rasterio.open(asset["href"]) as r:
        dn = r.read(1, out_shape=shape, resampling=Resampling.average) if shape else r.read(1)
    x = dn.astype("float32") * rb.get("scale", 0.0001) + (0.0 if offset_applied else rb.get("offset", 0.0))
    x[dn == 0] = np.nan
    return x


def tile_reference(item):
    a = item["assets"]
    applied = bool(item["properties"].get("earthsearch:boa_offset_applied", False))
    with rasterio.open(a["scl"]["href"]) as r:
        scl, crs, transform = (r.read(1), r.crs, r.transform)
    swir = reflectance(a["swir16"], applied)
    green = reflectance(a["green"], applied, shape=scl.shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (green - swir) / (green + swir)
    bad = (
        binary_dilation(np.isin(scl, CLOUDY_SCL), iterations=3) | np.isin(scl, BAD_SCL) | ~np.isfinite(mndwi)
    )
    ref = np.where(bad, 255, mndwi > 0).astype("uint8")
    return (ref, scl, crs, transform)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", required=True, help="reference GeoTIFF (the L-band ascending 20 m grid)")
    ap.add_argument("--dates", nargs="+", required=True, help="UTC dates of the Sentinel-2 acquisitions")
    ap.add_argument("--out-dir", default="data/work/ref")
    ap.add_argument("--max-cloud", type=float, default=80.0, help="skip tiles cloudier than this (%%)")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    with rasterio.open(a.grid) as g:
        gcrs, gtr, shape, gbounds = (g.crs, g.transform, (g.height, g.width), g.bounds)
    bbox = transform_bounds(gcrs, "EPSG:4326", *gbounds)
    for date in a.dates:
        items = [i for i in search(date, bbox) if i["properties"].get("eo:cloud_cover", 100) <= a.max_cloud]
        items.sort(key=lambda i: i["properties"].get("eo:cloud_cover", 100))
        ref = np.full(shape, 255, "uint8")
        sclo = np.zeros(shape, "uint8")
        used = []
        for item in items:
            t_ref, t_scl, crs, tr = tile_reference(item)
            h, w = t_ref.shape
            tb = transform_bounds(crs, gcrs, tr.c, tr.f + h * tr.e, tr.c + w * tr.a, tr.f)
            fw = from_bounds(*tb, transform=gtr)
            c0, r0 = (max(int(np.floor(fw.col_off)), 0), max(int(np.floor(fw.row_off)), 0))
            c1 = min(int(np.ceil(fw.col_off + fw.width)), shape[1])
            r1 = min(int(np.ceil(fw.row_off + fw.height)), shape[0])
            if c1 <= c0 or r1 <= r0:
                continue
            win = Window(c0, r0, c1 - c0, r1 - r0)
            wtr = rasterio.windows.transform(win, gtr)
            sl = (slice(win.row_off, win.row_off + win.height), slice(win.col_off, win.col_off + win.width))
            for src, dst, nod in ((t_ref, ref, 255), (t_scl, sclo, 0)):
                tmp = np.full((win.height, win.width), nod, "uint8")
                reproject(
                    src,
                    tmp,
                    src_transform=tr,
                    src_crs=crs,
                    dst_transform=wtr,
                    dst_crs=gcrs,
                    resampling=Resampling.nearest,
                    src_nodata=nod,
                    dst_nodata=nod,
                )
                sub = dst[sl]
                fill = (ref[sl] == 255) & (tmp != nod) if dst is ref else (sub == 0) & (tmp != 0)
                sub[fill] = tmp[fill]
            ok = t_ref != 255
            used.append(
                f"{item['id']}@{item['properties']['datetime'][:19]}Z(cloud {item['properties'].get('eo:cloud_cover', -1):.0f}%)"
            )
            print(
                f"  {item['id']}: clear {ok.mean():.2f}, water {((t_ref[ok] == 1).mean() if ok.any() else 0):.3f}",
                flush=True,
            )
        out = os.path.join(a.out_dir, f"s2_water_{date.replace('-', '')}_20m.tif")
        prof = dict(
            driver="GTiff",
            height=shape[0],
            width=shape[1],
            count=2,
            dtype="uint8",
            crs=gcrs,
            transform=gtr,
            nodata=255,
            tiled=True,
            blockxsize=512,
            blockysize=512,
            compress="DEFLATE",
        )
        with rasterio.open(out, "w", **prof) as f:
            f.write(ref, 1)
            f.write(sclo, 2)
            f.update_tags(
                source="Sentinel-2 L2A (Earth Search)",
                date_utc=date,
                tiles=";".join(used),
                band1="0 land, 1 water (MNDWI > 0), 255 no reference",
                band2="SCL class (nearest)",
                cloud_mask="SCL 3,8,9,10 dilated 3 px; SCL 0,1,11",
            )
        v = ref != 255
        print(
            f"{date}: {len(used)} tiles -> {out}; reference on {v.mean():.1%} of the grid, water {(ref[v] == 1).mean():.2%} of it",
            flush=True,
        )


if __name__ == "__main__":
    main()
