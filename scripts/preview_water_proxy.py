#!/usr/bin/env python3
"""Quick look, no login: estimate when the floodplain was wettest from NASA's free NISAR preview PNGs.

Downloads the ~160 m 'LATLON' preview of every ascending (track 98, frame 14) acquisition listed
in the inventory, counts dark pixels (a rough open-water proxy) in a Ganga/Kosi floodplain window and
in the 20 km reference box, and saves a contact sheet. Previews are 8-bit colour images, so this
only ranks dates; all real analysis uses calibrated GCOV files.

    python scripts/preview_water_proxy.py
"""
import argparse
import csv
import os

import numpy as np
import requests
from PIL import Image, ImageDraw

# Preview image bounds for frame 98/14 (from the preview's KML, 2026-11-02) and frame footprint (from ASF)
W, E, S, N = 84.4449180459344, 87.88353293721326, 23.216527502912513, 26.27952248342344
FOOT = [(87.83752, 23.99011), (87.24748, 26.06452), (84.73054, 25.44132), (85.35437, 23.37826)]
BOX = (86.3946, 25.4098, 86.6054, 25.5902)  # reference box W, S, E, N


def inside(lon, lat, poly):
    c = np.zeros(lon.shape, bool)
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        c ^= ((y1 > lat) != (y2 > lat)) & (lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1)
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", default="data/inventory/nisar_L_gcov_inventory.csv")
    ap.add_argument("--preview-dir", default="data/previews")
    ap.add_argument("--csv-out", default="data/inventory/preview_water_proxy_ascending.csv")
    ap.add_argument("--sheet-out", default="docs/figures/ascending_previews_floodplain.jpg")
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.inventory)) if r["direction"] == "ASCENDING"
            and r["use_this_one"] == "True" and r["browse_latlon_png"]]
    os.makedirs(a.preview_dir, exist_ok=True)
    files = []
    for r in rows:
        p = os.path.join(a.preview_dir, f"A_{r['date_utc']}.png")
        if not os.path.exists(p):
            resp = requests.get(r["browse_latlon_png"], timeout=120); resp.raise_for_status()
            open(p, "wb").write(resp.content)
        files.append((r["date_utc"], r["maturity"], p))

    h, w = np.asarray(Image.open(files[0][2])).shape[:2]
    lon = W + (np.arange(w) + 0.5) * (E - W) / w
    lat = N - (np.arange(h) + 0.5) * (N - S) / h
    LON, LAT = np.meshgrid(lon, lat)
    inner = inside(LON, LAT, FOOT)
    flood = inner & (LAT > 25.0) & (LAT < 25.95) & (LON > 85.6) & (LON < 87.6)
    box = (LON > BOX[0]) & (LON < BOX[2]) & (LAT > BOX[1]) & (LAT < BOX[3])

    out, tiles = [], []
    x0, x1 = np.searchsorted(lon, 85.9), np.searchsorted(lon, 87.1)
    y0, y1 = np.searchsorted(-lat, -25.85), np.searchsorted(-lat, -25.15)
    for date, maturity, p in files:
        im = np.asarray(Image.open(p).convert("RGB")).astype(float)
        gray, valid = im.mean(axis=2), im.max(axis=2) > 0
        out.append({"date_utc": date, "maturity": maturity,
                    "floodplain_dark_fraction": round(float((gray[flood & valid] < 45).mean()), 4),
                    "reference_box_dark_fraction": round(float((gray[box & valid] < 45).mean()), 4)})
        t = Image.open(p).convert("RGB").crop((x0, y0, x1, y1))
        d = ImageDraw.Draw(t)
        bx = [int((v - 85.9) / (E - W) * w) for v in (BOX[0], BOX[2])]
        by = [int((25.85 - v) / (N - S) * h) for v in (BOX[3], BOX[1])]
        d.rectangle((bx[0], by[0], bx[1], by[1]), outline=(255, 255, 0), width=2)
        d.rectangle((0, 0, 120, 16), fill=(0, 0, 0)); d.text((3, 2), date, fill=(255, 255, 255))
        tiles.append(t)

    os.makedirs(os.path.dirname(a.csv_out) or ".", exist_ok=True)
    with open(a.csv_out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0])); wr.writeheader(); wr.writerows(out)
    peak = max(out, key=lambda r: r["floodplain_dark_fraction"])
    for r in out:
        print(r["date_utc"], r["maturity"][:4], f"floodplain {r['floodplain_dark_fraction']:.3f}",
              f"box {r['reference_box_dark_fraction']:.3f}", "<- wettest floodplain" if r is peak else "")

    tw, th = tiles[0].size
    cols = 4
    rws = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 4, rws * th + (rws - 1) * 4), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
    os.makedirs(os.path.dirname(a.sheet_out) or ".", exist_ok=True)
    sheet.save(a.sheet_out, quality=85)
    print("contact sheet ->", a.sheet_out)


if __name__ == "__main__":
    main()
