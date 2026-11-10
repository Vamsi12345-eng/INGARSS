# INGARSS

Surface-water mapping and change detection over the Ganga floodplain in Bihar, India, using NISAR L- and S-band SAR (L2 GCOV). Built for the InGARSS 2026 Young Professionals Hackathon, Phase 1. The core question is whether combining L and S beats either band alone. See [PLAN.md](PLAN.md) for the plan, data facts, known product issues and status, and [docs/technical_note.md](docs/technical_note.md) ([PDF](docs/technical_note.pdf)) for the method and results.

- Technical documentation: [docs/technical_note.pdf](docs/technical_note.pdf) (Word version: [docs/technical_note.docx](docs/technical_note.docx))
- Presentation: [docs/Drishya_NISAR_presentation.pdf](docs/Drishya_NISAR_presentation.pdf) (PowerPoint: [docs/Drishya_NISAR_presentation.pptx](docs/Drishya_NISAR_presentation.pptx))
- Code: [scripts_main/](scripts_main/) — step-by-step run guide in [scripts_main/README.md](scripts_main/README.md)

**Result:** against Sentinel-2, the Bayesian L+S water map beats L-band only and S-band only on both validated dates: F1 0.698 vs 0.671 / 0.672 on 18 Oct 2026, and 0.799 vs 0.752 / 0.774 at the 12 Sep peak. The 95% CIs of the gains exclude zero, and an equal-information control (L with about 4× the looks) does worse, so the gain comes from the second frequency.

## Layout

```
PLAN.md                    plan, data facts, status, checklist
docs/technical_note.md     technical note (method, results, uncertainty, limitations)
docs/results/              validation, change and polarimetry results (JSON)
docs/figures/              figures
scripts/
  nisar_inventory.py       list L-band GCOV granules for our frames (ASF public API, no login)
  preview_water_proxy.py   rank dates by water extent from free preview images (no login)
  fetch_nisar_l.py         download L-band GCOV (needs EARTHDATA_TOKEN), optionally shrink to 20 m
  bhoonidhi_s_band.py      search/download S-band GCOV from ISRO Bhoonidhi (needs BHOONIDHI_USER/PASSWORD)
  gcov_to_cog.py           GCOV HDF5 -> 20 m Cloud-Optimized GeoTIFFs (L- or S-band, full frame, mask-aware)
  fetch_ancillary.py       HAND, DEM/slope, WorldCover, JRC water on the 20 m grid (no login)
  fetch_s2_reference.py    Sentinel-2 MNDWI water reference on the 20 m grid (no login)
  coreg_check.py           sub-pixel L-vs-S co-registration on the shared 20 m grid
  water_maps.py            P(water) and water maps: L, S, L+S, L4x control, AND, OR (one algorithm)
  change_maps.py           stable water / new water / water loss between two dates
  validate.py              accuracy vs Sentinel-2 with block-bootstrap CIs, McNemar, adjusted areas
  polarimetry_quicklook.py L quad-pol Pauli and HH-VV phase, S compact-pol m-chi (14 Sep)
  make_figures.py          figures for the note and slides
  run_analysis.sh          everything after the downloads, in order
data/inventory/            granule inventories and the preview water ranking (committed)
data/raw/, data/work/      downloads and intermediate rasters (not committed)
```

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python scripts/fetch_nisar_l.py --direction A --dates 2026-07-14 2026-09-12 2026-10-18 --convert --delete-raw
```

```bash
python scripts/bhoonidhi_s_band.py download --convert --delete-raw --ids <S-band ids from data/inventory/nisar_S_gcov_inventory.csv>
```

```bash
python scripts/fetch_ancillary.py --warp-to data/work/L/<granule>_HHHH_20m.tif
```

```bash
./scripts/run_analysis.sh
```

The exact S-band IDs and the descending quad-pol and compact-pol commands are in PLAN.md (next step 1). Credentials are read from environment variables (`EARTHDATA_TOKEN`, `BHOONIDHI_USER`, `BHOONIDHI_PASSWORD`). Never commit them.
