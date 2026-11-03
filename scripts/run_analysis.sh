#!/usr/bin/env bash
# Full analysis after the 20 m GCOV files and supporting layers exist (see PLAN.md for the downloads):
# water maps (L, S, L+S, L4x, AND, OR) per date -> change maps -> validation against Sentinel-2 -> figures.
# Memory: about 6-7 GB per water-map run on a joint L+S date, 9 GB for a change-map run; with 16 GB RAM run
# at most two water-map runs at once and nothing else beside them (a third job got one run killed on 3 Nov).
set -euo pipefail
cd "$(dirname "$0")/.."
GRID=$(ls data/work/L/NISAR_L2_*_098_A_014_*_20261018T*_HHHH_20m.tif | head -1)

# Sentinel-2 reference (MNDWI) for the validation dates: 18 Oct (same UTC day as the NISAR pass) and
# 13 Sep (about 5 h after the 12 Sep peak pass)
[ -f data/work/ref/s2_water_20261018_20m.tif ] && [ -f data/work/ref/s2_water_20260913_20m.tif ] || \
  python scripts/fetch_s2_reference.py --grid "$GRID" --dates 2026-10-18 2026-09-13

# water maps for the three joint L+S dates. 20 Jun (L only) is not run: with the same algorithm it maps
# 46% of the frame as water (dry, smooth pre-monsoon fields are as dark as water at L-band) - see PLAN.md
python scripts/water_maps.py --date 2026-10-18 > data/logs/water_20261018.log 2>&1 &
python scripts/water_maps.py --date 2026-09-12 > data/logs/water_20260912.log 2>&1 &
wait
python scripts/water_maps.py --date 2026-07-14 > data/logs/water_20260714.log 2>&1
for d in 20261018 20260912 20260714; do
  [ -f "data/work/maps/water_${d}_summary.json" ] || { echo "water maps for $d missing: see data/logs/water_$d.log"; exit 1; }
done

# change: gain (14 Jul -> 12 Sep, the first joint low-water date to the peak) and loss (12 Sep -> 18 Oct)
python scripts/change_maps.py --dates 2026-07-14 2026-09-12
python scripts/change_maps.py --dates 2026-09-12 2026-10-18

# validation against Sentinel-2
python scripts/validate.py --date 2026-10-18 --ref data/work/ref/s2_water_20261018_20m.tif
python scripts/validate.py --date 2026-09-12 --ref data/work/ref/s2_water_20260913_20m.tif

# polarimetry quick look (14 Sep descending: L quad-pol HHVV kept, S compact-pol) and figures
python scripts/polarimetry_quicklook.py
python scripts/make_figures.py
