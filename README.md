# INGARSS

Surface-water mapping and change detection over the Ganga floodplain in Bihar, India, using NISAR L- and S-band SAR (L2 GCOV). Built for the InGARSS 2026 Young Professionals Hackathon, Phase 1. The core question is whether combining L and S beats either band alone. See [PLAN.md](PLAN.md) for the full plan, data facts, known product issues and schedule.

## Layout

```
PLAN.md                  plan, data facts, schedule, checklist
scripts/
  nisar_inventory.py     list L-band GCOV granules for our frames (ASF public API, no login)
  preview_water_proxy.py rank dates by water extent from free preview images (no login)
  fetch_nisar_l.py       download L-band GCOV (needs EARTHDATA_TOKEN), optionally shrink to 20 m
  gcov_to_cog.py         GCOV HDF5 -> 20 m Cloud-Optimized GeoTIFFs (L- or S-band, full frame)
  bhoonidhi_s_band.py    search/download S-band GCOV from ISRO Bhoonidhi (needs BHOONIDHI_USER/PASSWORD)
data/inventory/          granule inventories and the preview water ranking (committed)
data/raw/, data/work/    downloads and intermediate rasters (not committed)
docs/figures/            figures
```

## Quick start

```bash
pip install -r requirements.txt
python scripts/nisar_inventory.py
python scripts/fetch_nisar_l.py --direction A --dates 2026-06-20 2026-09-12 2026-10-18 --convert --delete-raw
```

Credentials are read from environment variables (`EARTHDATA_TOKEN`, `BHOONIDHI_USER`, `BHOONIDHI_PASSWORD`). Never commit them.
