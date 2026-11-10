#!/usr/bin/env python3
import argparse
import glob
import json
import os
import time
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from sklearn.mixture import GaussianMixture

PIX_KM2 = 0.0004
RNG = np.random.default_rng(42)


def find(band, date):
    d = date.replace("-", "")
    hits = sorted(glob.glob(f"data/work/{band}/NISAR_{band}2_*_098_A_014_*_{d}T*_HHHH_20m.tif"))
    return hits[0][: -len("_HHHH_20m.tif")] if hits else None


def read_on_grid(path, ref, fill):
    with rasterio.open(path) as r:
        col = int(round((r.transform.c - ref.transform.c) / ref.transform.a))
        row = int(round((r.transform.f - ref.transform.f) / ref.transform.e))
        out = np.full((ref.height, ref.width), fill, r.dtypes[0])
        r0, c0 = (max(row, 0), max(col, 0))
        r1, c1 = (min(row + r.height, ref.height), min(col + r.width, ref.width))
        out[r0:r1, c0:c1] = r.read(1, window=Window(c0 - col, r0 - row, c1 - c0, r1 - r0))
    return out


def to_db(a):
    with np.errstate(divide="ignore", invalid="ignore"):
        return (10 * np.log10(a)).astype("float16")


def ki_threshold(x, lo=-35.0, hi=5.0, step=0.1):
    h, e = np.histogram(x, bins=np.arange(lo, hi + step, step))
    c = (e[:-1] + e[1:]) / 2
    p = h / max(h.sum(), 1)
    P1, m1, s1 = (np.cumsum(p), np.cumsum(p * c), np.cumsum(p * c * c))
    P2 = 1 - P1
    with np.errstate(all="ignore"):
        mu1, mu2 = (m1 / P1, (m1[-1] - m1) / P2)
        v1, v2 = (s1 / P1 - mu1**2, (s1[-1] - s1) / P2 - mu2**2)
        J = 1 + P1 * np.log(v1) + P2 * np.log(v2) - 2 * (P1 * np.log(P1) + P2 * np.log(P2))
    J[~np.isfinite(J) | (P1 < 0.01) | (P2 < 0.01)] = np.inf
    i = int(np.argmin(J))
    return (
        float(c[i] + step / 2),
        float(P1[i]),
        float(mu1[i]),
        float(np.sqrt(v1[i])),
        float(mu2[i]),
        float(np.sqrt(v2[i])),
    )


def split_threshold(hh, valid, tile=256):
    ts, pool, H, W = ([], [], hh.shape[0], hh.shape[1])
    for r in range(0, H - tile + 1, tile):
        for c in range(0, W - tile + 1, tile):
            v = valid[r : r + tile, c : c + tile]
            if v.mean() < 0.9:
                continue
            x = hh[r : r + tile, c : c + tile][v].astype("float32")
            t, p1, m1, s1, m2, s2 = ki_threshold(x)
            D = np.sqrt(2) * abs(m2 - m1) / np.sqrt(s1**2 + s2**2)
            if 0.1 <= p1 <= 0.9 and D >= 2 and (m1 < -14):
                ts.append(t)
                pool.append(x[::16])
    if len(ts) >= 5:
        t = float(np.median(ts))
        x = np.concatenate(pool)
    else:
        x = hh[valid][::7].astype("float32")
        t = ki_threshold(x, lo=-30.0, hi=-8.0)[0]
    d, b = (x[x <= t], x[x > t])
    return (
        (t, float(d.size / max(x.size, 1)), float(d.mean()), float(d.std()), float(b.mean()), float(b.std())),
        len(ts),
    )


def sample(mask, n):
    flat, total = (mask.ravel(), mask.size)
    frac = flat[RNG.integers(0, total, 200000)].mean()
    if frac * total < 20000000:
        idx = np.flatnonzero(flat)
        return RNG.choice(idx, min(n, idx.size), replace=False) if idx.size else idx
    out = np.empty(0, np.int64)
    for _ in range(20):
        k = int(min(50000000, (n - out.size) / frac * 1.3 + 1000))
        cand = RNG.integers(0, total, k)
        out = np.unique(np.concatenate([out, cand[flat[cand]]]))
        if out.size >= n:
            return RNG.choice(out, n, replace=False)
    return out


def features_at(feats, idx):
    return np.stack([f.ravel()[idx].astype("float32") for f in feats], axis=1)


def posterior(gw, gl, X, pi):
    lw, ll = (gw.score_samples(X), gl.score_samples(X))
    with np.errstate(over="ignore"):
        return 1.0 / (1.0 + np.exp(np.clip(ll - lw, -50, 50)) * (1 - pi) / pi)


def block40(a_db):
    H, W = (a_db.shape[0] // 2 * 2, a_db.shape[1] // 2 * 2)
    lin = np.power(10.0, a_db[:H, :W].astype("float32") / 10).reshape(H // 2, 2, W // 2, 2)
    with np.errstate(invalid="ignore"):
        m = np.nanmean(lin, axis=(1, 3))
    out = np.full(a_db.shape, np.nan, "float16")
    out[:H, :W] = to_db(np.repeat(np.repeat(m, 2, axis=0), 2, axis=1))
    return out


def classify(name, feats, valid, water_seeds, land_seeds, hill, prior_idx, shape):
    t0 = time.time()
    Xw, Xl = (features_at(feats, water_seeds), features_at(feats, land_seeds))
    Xw, Xl = (Xw[np.all(np.isfinite(Xw), axis=1)], Xl[np.all(np.isfinite(Xl), axis=1)])
    gw = GaussianMixture(1, covariance_type="full", random_state=0).fit(Xw)
    gl = GaussianMixture(3, covariance_type="full", random_state=0, n_init=2).fit(Xl)
    Xp = features_at(feats, prior_idx)
    ok = np.all(np.isfinite(Xp), axis=1)
    pi = water_seeds.size / (water_seeds.size + land_seeds.size)
    for _ in range(50):
        new = float(np.clip(posterior(gw, gl, Xp[ok], pi).mean(), 0.0001, 0.5))
        if abs(new - pi) < 1e-05:
            break
        pi = new
    P = np.full(shape, 255, "uint8")
    rows = 512
    for r0 in range(0, shape[0], rows):
        r1 = min(r0 + rows, shape[0])
        m = valid[r0:r1]
        if not m.any():
            continue
        X = np.stack([f[r0:r1][m].astype("float32") for f in feats], axis=1)
        block = P[r0:r1]
        block[m] = np.round(100 * posterior(gw, gl, X, pi)).astype("uint8")
    if hill is not None:
        P[hill & valid] = 0
    water = (P >= 50) & (P != 255)
    lab, n = ndimage.label(water, structure=np.ones((3, 3), bool))
    sizes = np.bincount(lab.ravel())
    small = sizes < 10
    small[0] = False
    water[small[lab]] = False
    del lab
    W = np.where(valid, water, 255).astype("uint8")
    info = dict(
        prior_water=round(pi, 5),
        water_km2=round(float(water.sum()) * PIX_KM2, 1),
        uncertain_km2=round(float(((P > 20) & (P < 80)).sum()) * PIX_KM2, 1),
        water_mean=np.round(gw.means_[0], 2).tolist(),
        land_means=np.round(gl.means_, 2).tolist(),
        land_weights=np.round(gl.weights_, 3).tolist(),
        seconds=round(time.time() - t0, 1),
    )
    print(
        f"  {name:4s} prior {pi:.4f}  water {info['water_km2']:9.1f} km2  uncertain {info['uncertain_km2']:8.1f} km2  ({info['seconds']} s)",
        flush=True,
    )
    return (P, W, info)


def write(path, P, W, ref, tags):
    prof = dict(
        driver="GTiff",
        height=ref.height,
        width=ref.width,
        count=2,
        dtype="uint8",
        crs=ref.crs,
        transform=ref.transform,
        nodata=255,
        tiled=True,
        blockxsize=512,
        blockysize=512,
        compress="DEFLATE",
    )
    with rasterio.open(path, "w", **prof) as f:
        f.write(P, 1)
        f.write(W, 2)
        f.update_tags(
            **tags,
            band1="P(water) percent, 255 outside domain",
            band2="water map (0 land, 1 water), 255 outside domain",
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="UTC date of the ascending pass, e.g. 2026-10-18")
    ap.add_argument(
        "--grid", default=None, help="L-band HHHH file that defines the grid (default: this date's)"
    )
    ap.add_argument("--ancillary", default="data/work/ancillary")
    ap.add_argument("--out-dir", default="data/work/maps")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    d = a.date.replace("-", "")
    L, S = (find("L", a.date), find("S", a.date))
    if L is None:
        raise SystemExit(f"no L-band file for {a.date}")
    grid = a.grid or sorted(glob.glob("data/work/L/NISAR_L2_*_098_A_014_*_HHHH_20m.tif"))[0]
    with rasterio.open(grid) as ref:
        print(
            f"{a.date}: L = {os.path.basename(L)}\n            S = {(os.path.basename(S) if S else 'none')}",
            flush=True,
        )
        bands = {"L": L} | ({"S": S} if S else {})
        db = {}
        for b, base in bands.items():
            for pol in ("HHHH", "HVHV"):
                db[f"{b}_{pol[:2]}"] = to_db(read_on_grid(f"{base}_{pol}_20m.tif", ref, np.nan))
        shape = (ref.height, ref.width)
        valid = np.ones(shape, bool)
        for v in db.values():
            valid &= np.isfinite(v)
        hill = seed_ok = None
        hand_p, slope_p = (
            os.path.join(a.ancillary, "hand_20m.tif"),
            os.path.join(a.ancillary, "slope_20m.tif"),
        )
        if os.path.exists(hand_p) and os.path.exists(slope_p):
            hand = read_on_grid(hand_p, ref, np.nan)
            slope = read_on_grid(slope_p, ref, np.nan)
            hill = (hand > 15) | (slope > 10)
            seed_ok = (hand < 10) & (slope < 5)
            del hand, slope
        summary = dict(
            date=a.date,
            L=os.path.basename(L),
            S=os.path.basename(S) if S else None,
            domain_km2=round(float(valid.sum()) * PIX_KM2, 1),
            hand_slope_used=hill is not None,
        )
        thr, dark, bright = ({}, valid.copy(), valid.copy())
        for b in bands:
            (t, p1, m1, s1, m2, s2), ntiles = split_threshold(db[f"{b}_HH"], valid)
            thr[b] = dict(
                threshold_db=round(t, 2), tiles=ntiles, dark_mean=round(m1, 2), bright_mean=round(m2, 2)
            )
            print(
                f"  {b} HH KI threshold {t:.2f} dB from {ntiles} bimodal tiles (dark {m1:.1f} +/- {s1:.1f}, bright {m2:.1f} +/- {s2:.1f})",
                flush=True,
            )
            hh = db[f"{b}_HH"]
            dark &= hh < t - 1.5
            bright &= hh > t + 1.5
        if seed_ok is not None:
            dark &= seed_ok
        summary["thresholds"] = thr
        ws, ls = (sample(dark, 300000), sample(bright, 600000))
        prior_idx = sample(valid, 1000000)
        summary["seeds"] = dict(water=int(ws.size), land=int(ls.size))
        print(f"  seeds: water {ws.size}, land {ls.size}", flush=True)
        sets = {"L": [db["L_HH"], db["L_HV"]]}
        if S:
            sets["S"] = [db["S_HH"], db["S_HV"]]
            sets["LS"] = [db["L_HH"], db["L_HV"], db["S_HH"], db["S_HV"]]
        tags = dict(date_utc=a.date, L_granule=summary["L"], S_granule=str(summary["S"]))
        results, maps = ({}, {})
        for name, feats in sets.items():
            P, W, info = classify(name, feats, valid, ws, ls, hill, prior_idx, shape)
            write(
                os.path.join(a.out_dir, f"water_{d}_{name}_20m.tif"), P, W, ref, dict(tags, feature_set=name)
            )
            results[name], maps[name] = (info, W)
            del P
        l4 = [block40(db["L_HH"]), block40(db["L_HV"])]
        v4 = valid & np.isfinite(l4[0]) & np.isfinite(l4[1])
        P, W, info = classify("L4x", l4, v4, ws, ls, hill, prior_idx, shape)
        W[~valid] = 255
        write(os.path.join(a.out_dir, f"water_{d}_L4x_20m.tif"), P, W, ref, dict(tags, feature_set="L4x"))
        results["L4x"] = info
        del P, W, l4
        if S:
            for name, op in (("AND", np.logical_and), ("OR", np.logical_or)):
                w = op(maps["L"] == 1, maps["S"] == 1)
                Wn = np.where(valid, w, 255).astype("uint8")
                Pn = np.where(valid, w * 100, 255).astype("uint8")
                write(
                    os.path.join(a.out_dir, f"water_{d}_{name}_20m.tif"),
                    Pn,
                    Wn,
                    ref,
                    dict(tags, feature_set=name),
                )
                results[name] = dict(water_km2=round(float(w[valid].sum()) * PIX_KM2, 1))
                print(f"  {name:4s} water {results[name]['water_km2']:9.1f} km2", flush=True)
        summary["feature_sets"] = results
        with open(os.path.join(a.out_dir, f"water_{d}_summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
        print(f"  -> {a.out_dir}/water_{d}_*_20m.tif", flush=True)


if __name__ == "__main__":
    main()
