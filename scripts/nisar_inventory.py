#!/usr/bin/env python3
"""List every NISAR L-band L2 GCOV granule for our two frames using ASF's public search API.

No login is needed for searching. Writes one CSV row per granule, marking the preferred
version of each acquisition (PROVISIONAL > BETA > URGENT_RESPONSE).

    python scripts/nisar_inventory.py --out data/inventory/nisar_L_gcov_inventory.csv
"""
import argparse
import csv
import json
import os
import urllib.parse
import urllib.request

ASF_SEARCH = "https://api.daac.asf.alaska.edu/services/search/param"
FRAMES = [(98, 14), (120, 76)]  # (relative orbit/track, frame): ascending, descending
RANK = {"PROVISIONAL": 0, "BETA": 1, "URGENT_RESPONSE": 2}


def search(track, frame):
    q = urllib.parse.urlencode({"dataset": "NISAR", "processingLevel": "GCOV", "relativeOrbit": track,
                                "frame": frame, "output": "jsonlite", "maxResults": 2000})
    with urllib.request.urlopen(f"{ASF_SEARCH}?{q}", timeout=120) as r:
        return json.load(r)["results"]


def row(r):
    n, g = r["nisar"], r["granuleName"]
    coll = r["collectionName"]
    maturity = "BETA" if "BETA" in coll else ("PROVISIONAL" if "PROVISIONAL" in coll else "URGENT_RESPONSE")
    size = [v["bytes"] for k, v in n["sizeMB"].items() if k == g + ".h5"]
    browse = [u for u in (r.get("browse") or []) if u.endswith("_LATLON.png")]
    return {
        "direction": r["flightDirection"], "track": r["path"], "frame": r["frame"],
        "date_utc": r["startTime"][:10], "time_utc": r["startTime"][11:19],
        "maturity": maturity, "crid": n.get("crid"), "orbit_type": n.get("orbitType"),
        "bandwidth_MHz": "+".join(n.get("rangeBandwidth") or []),
        "freqA_pols": "/".join(n.get("mainBandPolarization") or []),
        "freqB_pols": "/".join(n.get("sideBandPolarization") or []),
        "joint_L_S_observation": n.get("jointObservation"), "frame_coverage": n.get("frameCoverage"),
        "size_GB": round(size[0] / 1e9, 2) if size else "",
        "granule": g, "download_url": r["downloadUrl"],
        "browse_latlon_png": browse[0] if browse else "",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/inventory/nisar_L_gcov_inventory.csv")
    a = ap.parse_args()
    rows = [row(r) for t, f in FRAMES for r in search(t, f)]
    key = lambda x: (x["direction"], x["date_utc"], x["time_utc"][:5])
    best = {}
    for x in rows:
        if key(x) not in best or RANK[x["maturity"]] < RANK[best[key(x)]["maturity"]]:
            best[key(x)] = x
    for x in rows:
        x["use_this_one"] = best[key(x)] is x
    rows.sort(key=lambda x: (x["direction"], x["date_utc"], RANK[x["maturity"]]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} granules, {len(best)} unique acquisitions -> {a.out}")


if __name__ == "__main__":
    main()
