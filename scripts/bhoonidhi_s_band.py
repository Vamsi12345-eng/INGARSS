#!/usr/bin/env python3
"""Search and download NISAR S-band L2 GCOV from ISRO Bhoonidhi via its API.

Needs BHOONIDHI_USER and BHOONIDHI_PASSWORD environment variables (your Bhoonidhi login).
API docs: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/  (auth: 20 requests/hour/IP; download: 5 concurrent)

    # list S-band GCOV over the reference point for a date range (writes CSV + raw JSON)
    python scripts/bhoonidhi_s_band.py search --start 2026-06-01 --end 2026-11-02
    python scripts/bhoonidhi_s_band.py search --start 2026-01-01 --end 2026-02-28 --out data/inventory/s_jan_feb.csv
    # download chosen items by id (ids come from the search CSV), shrink each to 20 m, drop the 12.6 GB raw
    python scripts/bhoonidhi_s_band.py download --ids <id1> <id2> --convert --delete-raw

Tested live on 3 Nov 2026: an empty search returns HTTP 404 "NO RESULTS FOUND" (handled); about 1 in 3
TLS handshakes from the cloud session was reset (calls are retried); downloads ran at about 9 MB/s and
resume from a partial .part file.
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://bhoonidhi-api.nrsc.gov.in"
COLLECTION = "NISAR_SSAR_GCOV"
POINT = [86.5, 25.5]  # lon, lat of the reference-box centre


def _req(method, url, tries=6, **kw):
    """requests.request, retried when the connection drops. From the cloud session, about 1 in 3 TLS
    handshakes to the API was reset before the request was sent (3 Nov 2026), so a retry is safe."""
    for i in range(tries):
        try:
            return requests.request(method, url, **kw)
        except requests.ConnectionError as e:
            if i == tries - 1:
                raise
            wait = 2 ** (i + 1)
            print(f"  connection dropped ({type(e).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)


class Session:
    def __init__(self):
        self.user = os.environ.get("BHOONIDHI_USER", "").strip()
        pw = os.environ.get("BHOONIDHI_PASSWORD", "")
        if not (self.user and pw):
            sys.exit("Set BHOONIDHI_USER and BHOONIDHI_PASSWORD in the environment settings.")
        r = _req("POST", f"{API}/auth/token", json={"userId": self.user, "password": pw, "grant_type": "password"},
                 timeout=60)
        if r.status_code == 403:
            sys.exit("Bhoonidhi: max sessions already active. Log out elsewhere or wait, then retry.")
        r.raise_for_status()
        self._set(r.json())

    def _set(self, j):
        self.access, self.refresh_token = j["access_token"], j.get("refresh_token")
        self.expires = time.time() + int(j.get("expires_in", 1200)) - 60

    def refresh(self):
        r = _req("POST", f"{API}/auth/token", json={"userId": self.user, "refresh_token": self.refresh_token,
                                                     "grant_type": "refresh_token"}, timeout=60)
        r.raise_for_status()
        self._set(r.json())

    def headers(self):
        if time.time() > self.expires:
            self.refresh()
        return {"Authorization": f"Bearer {self.access}"}

    def logout(self):
        try:
            _req("POST", f"{API}/auth/logout", tries=3, headers={"Authorization": f"Bearer {self.refresh_token}"},
                 timeout=30)
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
    feats, seen, url, method = [], set(), f"{API}/data/search", "POST"
    while url:
        r = (_req("POST", url, json=body, headers=s.headers(), timeout=120) if method == "POST"
             else _req("GET", url, headers=s.headers(), timeout=120))
        if r.status_code == 401:
            s.refresh(); continue
        if r.status_code == 404 and "NO RESULTS" in r.text.upper():  # the API's answer to an empty search
            break
        r.raise_for_status()
        j = r.json()
        page = [f for f in j.get("features", []) if f.get("id") not in seen]
        if not page:  # empty or repeated page: stop even if the server still sends a "next" link
            break
        seen.update(f.get("id") for f in page)
        feats += page
        nxt = next((l for l in j.get("links", []) if l.get("rel") == "next"), None)
        url = nxt.get("href") if nxt else None
        method = (nxt or {}).get("method", "GET").upper()
        if nxt and "body" in nxt:  # STAC: "merge": true means merge into the previous body
            body = {**body, **nxt["body"]} if nxt.get("merge") else nxt["body"]
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


def fetch(s, item, raw_dir, tries=8):
    """Download one item to raw_dir; resumes with a Range request if the server supports it."""
    url = f"{API}/download?id={item}&collection={COLLECTION}"
    part = os.path.join(raw_dir, item + ".part")
    for attempt in range(1, tries + 1):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        h = dict(s.headers(), **({"Range": f"bytes={have}-"} if have else {}))
        try:
            with requests.get(url, headers=h, stream=True, timeout=(30, 600)) as r:
                if r.status_code == 401:
                    s.refresh(); continue
                if r.status_code == 404:
                    print(f"{item}: not on online storage (order it via Bhoonidhi Browse & Order)"); return None
                if r.status_code in (412, 429):
                    print(f"  HTTP {r.status_code}: download limit reached; waiting 60 s", flush=True)
                    time.sleep(60); continue
                if r.status_code == 416:  # stale .part from an earlier run: start over
                    os.remove(part); continue
                r.raise_for_status()
                if have and r.status_code != 206:  # server ignored Range: start over
                    have = 0
                print(f"  HTTP {r.status_code}, resuming at {have} B, " + ", ".join(
                    f"{k}={r.headers.get(k)}" for k in ("Content-Type", "Content-Length", "Accept-Ranges",
                                                        "Content-Disposition")), flush=True)
                m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', r.headers.get("Content-Disposition", ""))
                name = os.path.basename(m.group(1).strip()) if m else ""  # never trust a path from the server
                name = name if name and not name.startswith(".") else item + ".h5"
                total = int(r.headers.get("Content-Range", "/0").split("/")[-1] or 0) or \
                    (have + int(r.headers.get("Content-Length", 0)))
                got, last, t0 = have, have, time.time()
                with open(part, "ab" if have else "wb") as f:
                    for chunk in r.iter_content(8 * 1024 * 1024):
                        f.write(chunk); got += len(chunk)
                        if total and (got - last) > total / 20:
                            last = got
                            mbps = (got - have) / 1e6 / max(time.time() - t0, 1e-3)
                            print(f"  {item[:60]}... {100 * got / total:5.1f}%  {mbps:6.1f} MB/s", flush=True)
            if total and os.path.getsize(part) < total:
                raise IOError(f"incomplete: {os.path.getsize(part)} of {total} bytes")
            dest = os.path.join(raw_dir, name)
            os.replace(part, dest)
            print(f"{item} -> {dest} ({got / 1e9:.2f} GB, {(got - have) / 1e6 / max(time.time() - t0, 1e-3):.1f} MB/s)",
                  flush=True)
            return dest
        except (requests.RequestException, IOError) as e:
            wait = min(2 ** attempt * 5, 300)
            print(f"  attempt {attempt} failed ({e}); waiting {wait}s", flush=True); time.sleep(wait)
    print(f"{item}: giving up after {tries} attempts", flush=True)
    return None


def unpack(path, raw_dir):
    """Return the .h5 for a download: the file itself, or the .h5 extracted from a zip (flattened, no paths)."""
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.infolist() if m.filename.lower().endswith(".h5") and not m.is_dir()]
        if len(members) != 1:
            sys.exit(f"{path}: expected one .h5 inside, found {[m.filename for m in members]}")
        out = os.path.join(raw_dir, os.path.basename(members[0].filename))
        with z.open(members[0]) as src, open(out + ".part", "wb") as dst:
            shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
    os.replace(out + ".part", out)
    os.remove(path)
    print(f"  unzipped -> {out}")
    return out


def download(s, a):
    os.makedirs(a.raw_dir, exist_ok=True)
    for item in a.ids:
        done = sorted(f for f in os.listdir(a.raw_dir) if f.startswith(item) and not f.endswith(".part"))
        dest = os.path.join(a.raw_dir, done[0]) if done else fetch(s, item, a.raw_dir)
        if done:
            print(f"{item}: already downloaded ({dest})")
        if not dest:
            continue
        h5 = unpack(dest, a.raw_dir)
        if a.convert:
            subprocess.run([sys.executable, os.path.join(HERE, "gcov_to_cog.py"), h5, "--out-dir", a.out_dir,
                            "--spacing", str(a.spacing)] + (["--offdiag"] if a.offdiag else []), check=True)
            if a.delete_raw:
                os.remove(h5)
                print(f"  deleted {h5}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("search")
    s1.add_argument("--start", required=True); s1.add_argument("--end", required=True)
    s1.add_argument("--out", default="data/inventory/nisar_S_gcov_inventory.csv")
    s2 = sub.add_parser("download")
    s2.add_argument("--ids", nargs="+", required=True)
    s2.add_argument("--raw-dir", default="data/raw/S")
    s2.add_argument("--convert", action="store_true", help="run gcov_to_cog.py on each file after download")
    s2.add_argument("--out-dir", default="data/work/S", help="where --convert writes the 20 m GeoTIFFs")
    s2.add_argument("--spacing", type=float, default=20.0)
    s2.add_argument("--offdiag", action="store_true", help="also export complex off-diagonal terms (compact-pol)")
    s2.add_argument("--delete-raw", action="store_true", help="delete the .h5 after a successful conversion")
    a = ap.parse_args()
    s = Session()
    try:
        (search if a.cmd == "search" else download)(s, a)
    finally:
        s.logout()


if __name__ == "__main__":
    main()
