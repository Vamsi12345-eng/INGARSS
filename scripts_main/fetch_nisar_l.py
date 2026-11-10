#!/usr/bin/env python3
import argparse
import csv
import os
import subprocess
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK = 8 * 1024 * 1024


def pick(inv, direction, dates, granules):
    rows = list(csv.DictReader(open(inv)))
    if granules:
        sel = [r for r in rows if r["granule"] in set(granules)]
    else:
        d = {"A": "ASCENDING", "D": "DESCENDING"}[direction]
        sel = [
            r
            for r in rows
            if r["direction"] == d and r["date_utc"] in set(dates) and (r["use_this_one"] == "True")
        ]
    missing = set(granules or dates) - {r["granule"] if granules else r["date_utc"] for r in sel}
    if missing:
        sys.exit(f"Not in inventory: {sorted(missing)} (check data/inventory/nisar_L_gcov_inventory.csv)")
    return sel


def download(url, dest, token, retries=6):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    part = dest + ".part"
    for attempt in range(1, retries + 1):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        h = dict(headers, **{"Range": f"bytes={have}-"} if have else {})
        try:
            with requests.get(url, headers=h, stream=True, allow_redirects=True, timeout=(30, 300)) as r:
                if r.status_code == 401 or "urs.earthdata.nasa.gov" in r.url:
                    sys.exit(
                        "NASA login refused: set EARTHDATA_TOKEN (and open one NISAR file in your browser once to authorize ASF), then retry."
                    )
                if r.status_code == 416:
                    break
                r.raise_for_status()
                if have and r.status_code != 206:
                    have = 0
                total = int(r.headers.get("Content-Range", "/0").split("/")[-1] or 0) or have + int(
                    r.headers.get("Content-Length", 0)
                )
                t0, got, last = (time.time(), have, 0)
                with open(part, "ab" if have else "wb") as f:
                    for chunk in r.iter_content(CHUNK):
                        f.write(chunk)
                        got += len(chunk)
                        if total and got - last > total / 20:
                            last = got
                            mbps = (got - have) / 1000000.0 / max(time.time() - t0, 0.001)
                            print(
                                f"  {os.path.basename(dest)[:60]}... {100 * got / total:5.1f}%  {mbps:6.1f} MB/s",
                                flush=True,
                            )
            if total and os.path.getsize(part) < total:
                raise IOError(f"incomplete: {os.path.getsize(part)} of {total} bytes")
            break
        except (requests.RequestException, IOError) as e:
            wait = min(2**attempt, 60)
            print(f"  attempt {attempt} failed ({e}); retrying in {wait}s", flush=True)
            time.sleep(wait)
    else:
        sys.exit(f"Giving up on {url}")
    os.replace(part, dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", default="data/inventory/nisar_L_gcov_inventory.csv")
    ap.add_argument("--direction", choices=["A", "D"], default="A")
    ap.add_argument("--dates", nargs="*", default=[])
    ap.add_argument("--granules", nargs="*", default=[])
    ap.add_argument("--raw-dir", default="data/raw/L")
    ap.add_argument("--convert", action="store_true", help="run gcov_to_cog.py on each file after download")
    ap.add_argument("--out-dir", default="data/work/L", help="where --convert writes the 20 m GeoTIFFs")
    ap.add_argument("--spacing", type=float, default=20.0)
    ap.add_argument(
        "--offdiag", action="store_true", help="also export complex off-diagonal terms (quad-pol)"
    )
    ap.add_argument("--delete-raw", action="store_true", help="delete the .h5 after a successful conversion")
    a = ap.parse_args()
    if not (a.dates or a.granules):
        ap.error("give --dates or --granules")
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not token:
        print(
            "EARTHDATA_TOKEN is not set; trying anyway (works only if the environment injects NASA credentials)."
        )
    os.makedirs(a.raw_dir, exist_ok=True)
    for r in pick(a.inventory, a.direction, a.dates, a.granules):
        dest = os.path.join(a.raw_dir, r["granule"] + ".h5")
        print(f"{r['direction']} {r['date_utc']} {r['maturity']} {r['size_GB']} GB -> {dest}", flush=True)
        if not os.path.exists(dest):
            download(r["download_url"], dest, token)
        if a.convert:
            subprocess.run(
                [
                    sys.executable,
                    os.path.join(HERE, "gcov_to_cog.py"),
                    dest,
                    "--out-dir",
                    a.out_dir,
                    "--spacing",
                    str(a.spacing),
                ]
                + (["--offdiag"] if a.offdiag else []),
                check=True,
            )
            if a.delete_raw:
                os.remove(dest)
                print(f"  deleted {dest}")


if __name__ == "__main__":
    main()
