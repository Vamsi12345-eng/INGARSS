# scripts_main: how to run the pipeline

Team Drishya, InGARSS 2026 YP Hackathon (Phase 1). NISAR L- and S-band GCOV surface-water mapping and change detection over the Bihar Ganga floodplain.

Run every command from the repository root (the folder that contains `scripts_main/`).

## 0. Setup

```bash
pip install -r requirements.txt
```

Set your credentials as environment variables (needed only for steps 1 and 2):

```bash
export EARTHDATA_TOKEN=<NASA Earthdata token>
export BHOONIDHI_USER=<Bhoonidhi user id>
export BHOONIDHI_PASSWORD=<Bhoonidhi password>
```

Disk: about 30 GB free. Each download is converted to 20 m and the raw file deleted, so only one large file is on disk at a time.

## 1. Download L-band GCOV (NASA ASF) and convert to 20 m

```bash
python scripts_main/fetch_nisar_l.py --direction A --dates 2026-07-14 2026-09-12 2026-10-18 --convert --delete-raw
python scripts_main/fetch_nisar_l.py --direction D --dates 2026-09-14 --convert --offdiag --delete-raw
```

Output: `data/work/L/<granule>_HHHH_20m.tif`, `_HVHV_20m.tif`, `_numberOfLooks_20m.tif`, `_mask_20m.tif` (plus VVVV, VHVH and the complex off-diagonal terms for the 14 Sep quad-pol pass).
Time: about 5 min per date (7–9 GB each).

## 2. Download S-band GCOV (ISRO Bhoonidhi) and convert to 20 m

```bash
python scripts_main/bhoonidhi_s_band.py download --convert --delete-raw --ids \
    NISAR_S2_PR_GCOV_025_098_A_014_3700_DHNA_A_20260714T233811_20260714T233848_P00500_M_F_I_001 \
    NISAR_S2_UR_GCOV_030_098_A_014_3700_DHNA_A_20260912T233809_20260912T233846_P00500_N_F_I_001 \
    NISAR_S2_PR_GCOV_033_098_A_014_3700_DHNA_A_20261018T233810_20261018T233847_P00500_M_F_I_001
python scripts_main/bhoonidhi_s_band.py download --convert --offdiag --delete-raw --ids \
    NISAR_S2_PR_GCOV_030_120_D_076_2500_CRNA_A_20260914T125059_20260914T125135_P00500_M_F_I_001
```

Output: `data/work/S/<granule>_HHHH_20m.tif`, `_HVHV_20m.tif`, `_numberOfLooks_20m.tif`, `_mask_20m.tif`, `_inputDataExceptionMask_20m.tif` (RHRH, RVRV, RHRV for the 14 Sep compact-pol pass).
Time: about 25 min per date (12.6 GB each).

To list available S-band products: `python scripts_main/bhoonidhi_s_band.py search --start 2026-06-01 --end 2026-11-02`

## 3. Supporting layers (no login)

```bash
python scripts_main/fetch_ancillary.py --warp-to data/work/L/NISAR_L2_PR_GCOV_033_098_A_014_4005_DHDH_A_20261018T233811_20261018T233845_P05023_N_F_J_001_HHHH_20m.tif
```

Output: `data/work/ancillary/hand_20m.tif`, `slope_20m.tif`, `dem_20m.tif`, `worldcover_20m.tif`, `jrc_occurrence_20m.tif`, `jrc_seasonality_20m.tif`, all on the same 20 m grid.
Time: about 10 min.

## 4. Analysis: one command for steps 4a–4f

```bash
./scripts_main/run_analysis.sh
```

Time: about 45 min. It runs, in order:

| Step | Script | Output |
|---|---|---|
| 4a | `fetch_s2_reference.py` | Sentinel-2 MNDWI water reference: `data/work/ref/s2_water_20261018_20m.tif`, `s2_water_20260913_20m.tif` |
| 4b | `water_maps.py` (per date) | `data/work/maps/water_<date>_<set>_20m.tif` for set = L, S, LS, L4x, AND, OR (band 1: P(water) %, band 2: water map) and `water_<date>_summary.json` |
| 4c | `change_maps.py` | `data/work/maps/change_<d1>_<d2>_<set>_20m.tif` (0 stable land, 1 stable water, 2 new water, 3 water loss) and `docs/results/change_<d1>_<d2>.json` |
| 4d | `validate.py` | `docs/results/validation_<date>.json`: F1, precision, recall, IoU with 95% CIs, McNemar tests, adjusted areas |
| 4e | `polarimetry_quicklook.py` | `docs/figures/fig_polarimetry.png`, `docs/results/polarimetry_20260914.json` |
| 4f | `make_figures.py` | `docs/figures/fig_water_zoom.png`, `fig_accuracy.png`, `fig_change_LS.png`, `fig_water_area.png`, `fig_by_landcover.png` |

Each step can also be run on its own, for example:

```bash
python scripts_main/water_maps.py --date 2026-10-18
python scripts_main/change_maps.py --dates 2026-07-14 2026-09-12
python scripts_main/validate.py --date 2026-10-18 --ref data/work/ref/s2_water_20261018_20m.tif
```

## 5. Expected results

| F1 vs Sentinel-2 | L only | S only | L+S |
|---|---|---|---|
| 18 Oct 2026 | 0.671 | 0.672 | 0.698 |
| 12 Sep 2026 (peak) | 0.752 | 0.774 | 0.799 |

Change (L+S): 3,774 km² of new water from 14 Jul to 12 Sep; 3,273 km² of water lost from 12 Sep to 18 Oct.

## Files

| File | Purpose |
|---|---|
| `fetch_nisar_l.py` | download L-band GCOV from NASA ASF |
| `bhoonidhi_s_band.py` | search and download S-band GCOV from ISRO Bhoonidhi |
| `gcov_to_cog.py` | convert a GCOV HDF5 file to 20 m GeoTIFFs (called by the two downloaders) |
| `fetch_ancillary.py` | HAND, slope, WorldCover, JRC water on the 20 m grid |
| `fetch_s2_reference.py` | Sentinel-2 water reference |
| `water_maps.py` | water probability and water maps: L, S, L+S and references |
| `change_maps.py` | change between two dates |
| `validate.py` | accuracy against Sentinel-2 |
| `polarimetry_quicklook.py` | L-band quad-pol and S-band compact-pol polarimetry, 14 Sep |
| `make_figures.py` | figures |
| `run_analysis.sh` | runs steps 4a–4f in order |
