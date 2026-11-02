#!/usr/bin/env python3
"""Search and download NISAR S-band L2 GCOV from ISRO Bhoonidhi via its API.

Needs BHOONIDHI_USER and BHOONIDHI_PASSWORD environment variables (your Bhoonidhi login).
API docs: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/  (auth: 20 requests/hour/IP; download: 5 concurrent)

    # list S-band GCOV over the reference point for a date range (writes CSV + raw JSON)
    python scripts/bhoonidhi_s_band.py search --start 2026-06-01 --end 2026-11-02
    python scripts/bhoonidhi_s_band.py search --start 2026-01-01 --end 2026-02-28 --out data/inventory/s_jan_feb.csv
    # download chosen items by id (ids come from the search CSV)
    python scripts/bhoonidhi_s_band.py download --ids <id1> <id2>

Not yet tested against the live API (needs credentials): check the first run's output.
"""
import argparse
import csv
import json
import os
import re
import sys
import time

import requests

API = "https://bhoonidhi-api.nrsc.gov.in"
COLLECTION = "NISAR_SSAR_GCOV"
POINT = [86.5, 25.5]  # lon, lat of the reference-box centre


class Session:
    def __init__(self):
        self.user = os.environ.get("BHOONIDHI_USER", "").strip()
        pw = os.environ.get("BHOONIDHI_PASSWORD", "")
        if not (self.user and pw):
            sys.exit("Set BHOONIDHI_USER and BHOONIDHI_PASSWORD in the environment settings.")
        r = requests.post(f"{API}/auth/token", json={"userId": self.user, "password": pw, "grant_type": "password"},
                          timeout=60)
        if r.status_code == 403:
            sys.exit("Bhoonidhi: max sessions already active. Log out elsewhere or wait, then retry.")
        r.raise_for_status()
        self._set(r.json())

    def _set(self, j):
        self.access, self.refresh_token = j["access_token"], j.get("refresh_token")
        self.expires = time.time() + int(j.get("expires_in", 1200)) - 60

    def refresh(self):
        r = requests.post(f"{API}/auth/token", json={"userId": self.user, "refresh_token": self.refresh_token,
                                                      "grant_type": "refresh_token"}, timeout=60)
        r.raise_for_status()
        self._set(r.json())

    def headers(self):
        if time.time() > self.expires:
            self.refresh()
        return {"Authorization": f"Bearer {self.access}"}

    def logout(self):
        try:
            requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {self.refresh_token}"}, timeout=30)
        except requests.RequestException:
            pass


def flatten(feature):
    p = dict(feature.get("properties") or {})
    row = {"id": feature.get("id"), "collection": feature.get("collection", COLLECTION)}
    for k, v in p.items():
        row[k] = v if isinstance(v, (str, int, float, bool)) or v is None else json.dumps(v)
    if feature.get("bbox"):
        row["bbox"] = json.dumps(feature["bbox"])
    return row


def search(s, a):
    body = {"collections": [COLLECTION], "datetime": f"{a.start}T00:00:00Z/{a.end}T23:59:59Z",
            "intersects": {"type": "Point", "coordinates": POINT}, "limit": 500}
    feats, url, method = [], f"{API}/data/search", "POST"
    while url:
        r = (requests.post(url, json=body, headers=s.headers(), timeout=120) if method == "POST"
             else requests.get(url, headers=s.headers(), timeout=120))
        if r.status_code == 401:
            s.refresh(); continue
        r.raise_for_status()
        j = r.json()
        feats += j.get("features", [])
        nxt = next((l for l in j.get("links", []) if l.get("rel") == "next"), None)
        url = nxt.get("href") if nxt else None
        method = (nxt or {}).get("method", "GET").upper()
        body = (nxt or {}).get("body", body)
        time.sleep(0.4)  # stay under 3 requests/second
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(feats, open(a.out.rsplit(".", 1)[0] + ".json", "w"), indent=1)
    rows = sorted((flatten(f) for f in feats), key=lambda r: str(r.get("datetime", "")))
    if not rows:
        print("No S-band GCOV found for that date range over the reference point.")
        return
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("id", "datetime"), k))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} items -> {a.out}\nproperty names: {keys}\n")
    want = [k for k in keys if re.search(r"datetime|online|polari|node|direction|pass|track|frame|mode|size", k, re.I)]
    for r in rows:
        print("  ", r["id"], " | ".join(f"{k}={r.get(k)}" for k in want))


def download(s, a):
    os.makedirs(a.raw_dir, exist_ok=True)
    for item in a.ids:
        url = f"{API}/download?id={item}&collection={COLLECTION}"
        for attempt in range(1, 7):
            try:
                with requests.get(url, headers=s.headers(), stream=True, timeout=(30, 600)) as r:
                    if r.status_code == 401:
                        s.refresh(); continue
                    if r.status_code == 404:
                        print(f"{item}: not on online storage (order it via Bhoonidhi Browse & Order)"); break
                    if r.status_code == 412:
                        print("  too many concurrent downloads; waiting 60 s"); time.sleep(60); continue
                    r.raise_for_status()
                    cd = r.headers.get("Content-Disposition", "")
                    m = re.search(r'filename="?([^";]+)', cd)
                    dest = os.path.join(a.raw_dir, m.group(1) if m else f"{item}.h5")
                    total, got, t0 = int(r.headers.get("Content-Length", 0)), 0, time.time()
                    with open(dest + ".part", "wb") as f:
                        for chunk in r.iter_content(8 * 1024 * 1024):
                            f.write(chunk); got += len(chunk)
                    if total and got < total:
                        raise IOError(f"incomplete {got}/{total}")
                    os.replace(dest + ".part", dest)
                    print(f"{item} -> {dest} ({got / 1e9:.2f} GB, {got / 1e6 / max(time.time() - t0, 1e-3):.1f} MB/s)")
                    break
            except (requests.RequestException, IOError) as e:
                wait = min(2 ** attempt * 5, 300)
                print(f"  attempt {attempt} failed ({e}); waiting {wait}s"); time.sleep(wait)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("search")
    s1.add_argument("--start", required=True); s1.add_argument("--end", required=True)
    s1.add_argument("--out", default="data/inventory/nisar_S_gcov_inventory.csv")
    s2 = sub.add_parser("download")
    s2.add_argument("--ids", nargs="+", required=True)
    s2.add_argument("--raw-dir", default="data/raw/S")
    a = ap.parse_args()
    s = Session()
    try:
        (search if a.cmd == "search" else download)(s, a)
    finally:
        s.logout()


if __name__ == "__main__":
    main()
