#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
GRID=$(ls data/work/L/NISAR_L2_*_098_A_014_*_20261018T*_HHHH_20m.tif | head -1)

[ -f data/work/ref/s2_water_20261018_20m.tif ] && [ -f data/work/ref/s2_water_20260913_20m.tif ] || \
  python scripts_main/fetch_s2_reference.py --grid "$GRID" --dates 2026-10-18 2026-09-13

python scripts_main/water_maps.py --date 2026-10-18 > data/logs/water_20261018.log 2>&1 &
python scripts_main/water_maps.py --date 2026-09-12 > data/logs/water_20260912.log 2>&1 &
wait
python scripts_main/water_maps.py --date 2026-07-14 > data/logs/water_20260714.log 2>&1
for d in 20261018 20260912 20260714; do
  [ -f "data/work/maps/water_${d}_summary.json" ] || { echo "water maps for $d missing: see data/logs/water_$d.log"; exit 1; }
done

python scripts_main/change_maps.py --dates 2026-07-14 2026-09-12
python scripts_main/change_maps.py --dates 2026-09-12 2026-10-18

python scripts_main/validate.py --date 2026-10-18 --ref data/work/ref/s2_water_20261018_20m.tif
python scripts_main/validate.py --date 2026-09-12 --ref data/work/ref/s2_water_20260913_20m.tif

python scripts_main/polarimetry_quicklook.py
python scripts_main/make_figures.py
