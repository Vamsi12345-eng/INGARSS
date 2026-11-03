# InGARSS 2026 YP Hackathon (NISAR Phase 1): plan

**Deadline: 10 Nov 2026, 11:59 PM IST. Submit by about 6 PM IST that day.** Results are announced 15 Nov.

## The problem

Using only NISAR L2 GCOV data, map surface water and its change between dates (stable water, new water, water loss) over the full NISAR scene around Bihar's Ganga floodplain (centre 25.5°N, 86.5°E), three ways: L-band only, S-band only, and L+S combined.
The core question is whether combining L and S (plus the polarimetric channels, where available) measurably beats either band alone. The answer must be backed by validation metrics, honest uncertainty and reproducible code.

## Status and handoff (3 Nov 2026)

Done on 3 Nov:
- **S-band checked: Scenario A.** Bhoonidhi has 21 S-band GCOV items over the reference point for Jun–Nov 2026, all `Online=Y` (downloadable): `data/inventory/nisar_S_gcov_inventory.csv` (+ raw STAC JSON).
  - Ascending (track 98, frame 14), dual-pol HH/HV, full frame: PROVISIONAL on 14, 26 Jul; 19 Aug; 6, 18 Oct. Urgent-response only on 31 Aug, **12 Sep (the peak)**, 24 Sep, 30 Oct.
  - Descending (track 120, frame 76), compact-pol, full frame, PROVISIONAL: 21 Aug; 2, 14, 26 Sep (the quad-pol joint passes).
  - **None for 20 Jun, 2 Jul or 22 Jun**, and none for Nov 2025 – May 2026 (the Jan–Feb search returns "NO RESULTS FOUND"). Scenario B is not possible.
  - Also over the point: descending track 48 (frames 75/76), compact-pol, 28 Aug; 9, 21 Sep; 3 Oct. Our L-band inventory does not cover track 48.
- **Step-4 checks on real files (L 20 Jun, S 18 Oct)**:
  - x/yCoordinates are pixel centres. L-band says so (`pixel_coordinate_convention: center`). S-band (product spec 1.2.1) omits the attribute, but its coordinates sit on the same 5 m offsets, so its 20 m blocks fall exactly on the L-band 20 m lattice (offset 36 × 144 pixels, no resampling needed).
  - L 20 Jun output vs ASF preview: correlation peaks at zero shift (r = 0.53). Valid-swath corners match the file's `boundingPolygon`.
  - EPSG 32645 is read correctly from `projection.epsg_code`.
  - Mask codes: 0 = invalid (partially focused), 1..N = valid (sub-swath number), 255 = outside. L 20 Jun: 3.9% of the grid is 0. S 18 Oct: no 0s.
  - Terms: L dual-pol = HHHH, HVHV only. **S-band dual-pol also has complex HHHV.**
  - Precision: L-band covariance terms are stored with 16 mantissa bits. S-band terms use all 23.
  - **S-band "sample shift" flag.** `inputDataExceptionMask` = 64 ("NISAR SSAR sample shift") on 36% of the 18 Oct valid swath. Check co-registration and radiometry inside vs. outside it (next step 3).
- **`gcov_to_cog.py` fixes:**
  - Samples with mask 0 or 255 are now dropped before averaging. The old code averaged them in (3.9% of the 20 Jun grid). The 20 m mask follows the same rule as the data.
  - Covariance terms and looks are rounded to 16 mantissa bits, the precision of the L-band product (error ≤ 2⁻¹⁷, about 0.00003 dB). This makes them about 22% smaller. `--keep-bits 23` turns it off.
  - The exception mask is exported.
  - Ascending outputs are about 1.5 GB per date.
- **`bhoonidhi_s_band.py` tested live:**
  - About 1 in 3 TLS handshakes to the API is reset, so every call now retries.
  - An empty search returns HTTP 404 "NO RESULTS FOUND".
  - Downloads resume (`Accept-Ranges: bytes`), and server filenames are sanitized.
  - New options: `--convert`, `--offdiag`, `--delete-raw`.
  - S-band files are 12.6 GB and arrive at about 9 MB/s (about 25 min each). The web portal `bhoonidhi.nrsc.gov.in` refuses connections from the cloud session, but the API host works.
- **Downloads, 20 m outputs in `data/work/{L,S}/`** (local to the session, not committed):
  - L: A 20 Jun, 12 Sep, 18 Oct, and D 14 Sep with `--offdiag`.
  - S: A 18 Oct, 12 Sep (urgent-response), and D 14 Sep with `--offdiag`.
  - Some were still running when this was written; check `data/work/`.
- **Disk.** The session allowance is about 30 GB, so only one large raw file can be processed at a time.
  - When all the listed files are done, outputs are about 19 GB. D 14 Sep with off-diagonals is about 8 GB of that, because its native spacing is already 20 m.
  - That leaves about 10 GB for the supporting layers and analysis.

Done on 2 Nov:
- Scene inventory for both frames, built from ASF's public search API (no login): `data/inventory/nisar_L_gcov_inventory.csv`.
- Preview-based water ranking, also no login: `data/inventory/preview_water_proxy_ascending.csv` and `docs/figures/ascending_previews_floodplain.jpg`.
  - The floodplain was wettest on **12 Sep 2026**.
  - Water was lowest from 20 Jun to 14 Jul.
  - It was receding by 18–30 Oct. The reference box stayed wet until 6 Oct.
  - These are 8-bit previews at about 160 m, so the ranking is rough; confirm it with the calibrated data.
- Scripts in `scripts/`:
  - `nisar_inventory.py`: tested live.
  - `preview_water_proxy.py`: tested live.
  - `gcov_to_cog.py`: tested on a synthetic file that follows the documented layout only.
  - `fetch_nisar_l.py`: download untested; needs `EARTHDATA_TOKEN`.
  - `bhoonidhi_s_band.py`: untested; needs Bhoonidhi credentials.
  - `fetch_ancillary.py`: tested. Downloads JRC surface water, ESA WorldCover, GLO-30 HAND and DEM for both frames (about 2.7 GB, 4 minutes, no login) and aligns them to the 20 m grid.
- Sentinel-2 validation candidates (tile 45RVJ, cloud % for the whole tile):
  - 18 Oct: 12%, same day as the NISAR pass.
  - 13 Sep: 59%, about 5 hours after the peak pass.
  - 16 Jan: 0%. 6 Jan: 4%. 2 Nov: 8%. 20 Jun: 70%.
- Around the reference box: 74% cropland, and the height above the nearest river has a median of 0.4 m. JRC persistent water (occurrence ≥ 75%) covers only 0.5% of the area, against 8.8% water in WorldCover, because the rivers move. So use NISAR dry-season persistence as the main persistent-water layer, with JRC as a cross-check.

Credentials are expected as environment variables: `EARTHDATA_TOKEN`, `BHOONIDHI_USER`, `BHOONIDHI_PASSWORD`. Bhoonidhi's API needs the user ID and password in the request body, so they can't be network secrets. Never paste them into chat or commit them.

Next steps, in order:
1. Make sure every listed file is on the 20 m grid. To redo them in a fresh session (L-band about 5 min per file, S-band about 25 min):
   ```bash
   python scripts/fetch_nisar_l.py --direction A --dates 2026-06-20 2026-09-12 2026-10-18 --convert --delete-raw
   python scripts/fetch_nisar_l.py --direction D --dates 2026-09-14 --convert --offdiag --delete-raw
   python scripts/bhoonidhi_s_band.py download --convert --delete-raw --ids \
       NISAR_S2_PR_GCOV_033_098_A_014_3700_DHNA_A_20261018T233810_20261018T233847_P00500_M_F_I_001 \
       NISAR_S2_UR_GCOV_030_098_A_014_3700_DHNA_A_20260912T233809_20260912T233846_P00500_N_F_I_001
   python scripts/bhoonidhi_s_band.py download --convert --offdiag --delete-raw --ids \
       NISAR_S2_PR_GCOV_030_120_D_076_2500_CRNA_A_20260914T125059_20260914T125135_P00500_M_F_I_001
   ```
2. **Decide on 14 Jul (open).** 20 Jun has no S-band, so the only three-way L/S/L+S *gain* pair is 14 Jul → 12 Sep. 14 Jul is the earliest joint date, and the previews show water still low then. It needs L 14 Jul (7 GB raw) plus S 14 Jul (12.6 GB raw): about 3 GB of outputs, but a 12.6 GB raw doesn't fit next to all the other outputs. So either get it before the quad-pol file, or drop the D off-diagonals, or accept that the three-way change test uses only the 12 Sep → 18 Oct loss pair.
   ```bash
   python scripts/fetch_nisar_l.py --direction A --dates 2026-07-14 --convert --delete-raw
   python scripts/bhoonidhi_s_band.py download --convert --delete-raw --ids \
       NISAR_S2_PR_GCOV_025_098_A_014_3700_DHNA_A_20260714T233811_20260714T233848_P00500_M_F_I_001
   ```
3. Check L–S co-registration on 18 Oct (the same joint pass) by cross-correlating S HHHH against L HHHH. Do it separately inside and outside the S-band sample-shift flag. Repeat for 12 Sep: S-band there is urgent-response only, so check its geolocation before using it.
4. Align the supporting layers to the real grid: `python scripts/fetch_ancillary.py --warp-to data/work/L/<granule>_HHHH_20m.tif`.
5. Then follow the method and schedule below.

## Data facts (checked 2 Nov 2026)

| | Ascending (track 98, frame 14) | Descending (track 120, frame 76) |
|---|---|---|
| L-band mode | 40+5 MHz, HH/HV; frequency A at 10 m | 20+5 MHz **quad-pol** (HH/HV/VH/VV), 20 m, on joint L+S passes; 40+5 MHz HH/HV, L only, on the others |
| Joint L+S acquisitions | every pass | quad-pol passes only |
| BETA (pre-calibration) | 28 Nov, 10 Dec, 22 Dec 2025; 3, 15 Jan 2026 | 30 Nov, 24 Dec 2025; 5, 17 Jan 2026 (quad-pol) |
| PROVISIONAL (calibrated) | 20 Jun; 2, 14, 26 Jul; 19, 31 Aug; 12, 24 Sep; 6, 18 Oct 2026; 30 Oct (urgent-response version only so far) | quad-pol + joint: 22 Jun, 21 Aug, 2/14/26 Sep. HH/HV L-only: 4, 16 Jul; 8, 20 Oct; 1 Nov (urgent-response) |
| S-band GCOV on Bhoonidhi (checked 3 Nov) | 37 MHz HH/HV (+ complex HHHV), 10 m, full frame. PROVISIONAL: 14, 26 Jul; 19 Aug; 6, 18 Oct. Urgent-response only: 31 Aug, 12 Sep, 24 Sep, 30 Oct. None before 14 Jul | 25 MHz compact-pol, full frame, PROVISIONAL: 21 Aug; 2, 14, 26 Sep. None for 22 Jun |
| Overpass | 23:38 UTC = 05:08 IST on the next calendar day | 12:50 UTC = 18:20 IST |
| File size | L about 7 GB; S 12.6 GB | L about 7–9 GB |

- Both frames fully contain the 20 km reference box.
- Each frame covers about 62,000 km² (about 250 × 250 km): the Ganga plain in the north and the Jharkhand plateau (hills, reservoirs) in the south.
- Projection: UTM zone 45N (EPSG:32645).
- File dates are UTC. For the ascending pass, the local (IST) date is one day later.

## Known product issues and how we handle them

Sources: the ASF NISAR Data User Guide (availability page and PROVISIONAL known issues) and ISRO's Bhoonidhi NISAR page.

1. **Nothing before 17 Jun 2026 is calibrated.** BETA products are pre-calibration, and ASF warns against mixing BETA and PROVISIONAL. Never difference backscatter across BETA and PROVISIONAL. Scene-adaptive classification per date is acceptable, with the caveat stated.
2. **There is a permanent instrument data gap from 27 Jul to 10 Aug 2026.**
3. **Banding and dark artifacts can look like water.**
   - Joint-mode 40 MHz products (our ascending L+S data) have stronger-than-usual radiometric banding.
   - S-band shows banding over low-signal surfaces (including water), residual RFI, and dark "transmit-gap" stripes in fixed-PRF acquisitions.
   - Fix: normalize the median land γ⁰ in each incidence-angle bin, mask bins that drop sharply, and flag the remaining RFI.
4. **The quad-pol phase is miscalibrated by 59°.** Before any decomposition, multiply HVVH by e^(+j59°), and HHHV, HHVV and VHVV by e^(−j59°). HHVH, HVVV and the diagonal terms are unaffected. Do decompositions on PROVISIONAL dates only.
5. **Frequency B (5 MHz, 80 m) has larger calibration errors.** Use frequency A only.
6. **L-band dual-pol GCOV has no off-diagonal terms**, so HH/HV data support intensity features only. Full polarimetry is possible only with the descending quad-pol data and S-band compact-pol (check which terms ISRO includes).
7. **The RFI filter can leave residual interference or remove features in high-contrast areas** (such as water edges). Low-level ripples can also appear over dark areas.
8. **Use complete products.** Urgent-response products have forecast orbits (L-band); ISRO says S-band urgent-response products may cover a partial swath or a single polarization. Prefer PROVISIONAL or full products.
   - The S-band 12 Sep (peak) product exists only as urgent-response. Bhoonidhi lists it as full frame and HH/HV, so use it, but check its geolocation against L 12 Sep first.
9. **S-band "sample shift" flag** (found 3 Nov). `inputDataExceptionMask` = 64 ("NISAR SSAR sample shift") covers 36% of the 18 Oct valid swath. The product doesn't say what it does to the data.
   - Before fusing, compare L–S co-registration and S radiometry inside vs. outside the flag (it is exported as `*_inputDataExceptionMask_20m.tif`).
   - If they differ, mask the flagged area or report results separately for it.

## Scenarios

- **A: S-band exists for the 2026 monsoon (confirmed 3 Nov; this is the plan).** Run the L vs S vs L+S comparison on ascending joint passes (same time, same geometry). The change pairs are 20 Jun → 12 Sep (gain) and 12 Sep → 18 Oct (loss). Do polarimetry on descending quad-pol + S-band joint passes, starting with 14 Sep (two days after the ascending peak).
  - 20 Jun has no S-band. So the gain pair is L-only, unless 14 Jul (the first joint date) is added. See next step 2.
- **B: S-band only for Jan–Feb 2026.**
  - Run the three-way comparison on 3 and 15 Jan (ascending) and 5 and 17 Jan (descending). This is the dry season: a test of rivers vs sandbars.
  - 3 → 15 Jan doubles as a stable-period false-change test.
  - Monsoon change detection uses L-band only, with the limitation stated. The brief allows this.

### Download priority

| # | File | Why | Size |
|---|---|---|---|
| 1 | Ascending 2026-06-20 | low-water baseline (earliest calibrated date) | 7.0 GB |
| 2 | Ascending 2026-09-12 | peak water (from the previews) | 7.0 GB |
| 3 | Ascending 2026-10-18 | recession | 6.8 GB |
| 4 | Descending 2026-09-14 (quad-pol, use `--offdiag`) | polarimetry at peak | 8.9 GB |
| S1 | S-band ascending 2026-10-18 (PROVISIONAL) | joint with #3 | 12.6 GB |
| S2 | S-band ascending 2026-09-12 (urgent-response only) | joint with #2 | 12.6 GB |
| S3 | S-band descending 2026-09-14 (compact-pol, use `--offdiag`) | joint with #4 | |
| open | L + S ascending 2026-07-14 | joint low-water date for a three-way gain pair (next step 2) | 7.0 + 12.6 GB |
| 5 | Ascending 2026-08-31 and 2026-10-06 | water-area time series (optional) | 7.0 GB each |
| B | Ascending 2026-01-03 and 2026-01-15; Descending 2026-01-05 and 2026-01-17 | Scenario B only (BETA); no S-band exists for these dates | 7–9 GB each |

## Method

**Fairness rules.** These are what make the answer credible.
- Use one common grid: EPSG:32645 at 20 m, aligned to the L-band grid. Average in linear power, then convert to dB.
- Use the same algorithm, settings, training pixels, post-processing and validation samples for L, S and L+S. Only the input features change.
- Run an **equal-information control**: compare L+S against L+L (two L dates 12 days apart in a stable period) or against L with twice the looks. If L+S still wins, the gain comes from the second frequency, not just from more data.
- For every comparison, report the time gap, incidence angle and number of looks.
- Produce outputs over the full frame. Compute comparison metrics where L and S overlap.

**Tasks:**
- **A. Data review:** an inventory table (granule, CRID and maturity, mode, polarizations, covariance terms, pixel size, joint flag, QA notes), a footprint map, and an acquisition timeline showing the gap and the BETA/PROVISIONAL boundary.
- **Preprocessing:**
  - Read the diagonal terms as γ⁰ and apply the GCOV mask.
  - Remove banding as described in issue 3.
  - Use HAND (height above nearest drainage, from the Copernicus GLO-30 DEM) and slope to remove hill-shadow false water in the south.
- **B. Single band:** split-based automatic thresholding (Martinis 2015; Chini 2017).
  - Use ~5 km tiles and keep those with clearly two-peaked histograms.
  - Pick the threshold with Kittler–Illingworth; fit a two-class model to get P(water).
  - Grow regions, then apply a minimum mapping unit.
  - Use identical code for L and S.
- **C. Fusion (main innovation):** Bayesian likelihood fusion.
  - Fit class-conditional Gaussians (one water class, 2–3 non-water classes) on [L_HH, L_HV, S_HH, S_HV] in dB.
  - Seed the water class from persistent water.
  - Output P(water) with an uncertainty band (0.2–0.8).
  - Report naive AND/OR fusion as a reference.
  - Optional: LightGBM with spatial block cross-validation and SHAP.
- **D. Change:** compare the per-date probability maps to get stable water, gain, loss and stable non-water.
  - Per-pixel confidence: P(gain) = P₂·(1−P₁).
  - On PROVISIONAL-only pairs, also require a backscatter log-ratio of more than about 3 dB.
- **E. New water:**
  - Persistent water = water on at least 80% of the Nov–Jan dates, cross-checked against JRC Global Surface Water.
  - Report new water outside it as "potential temporary surface inundation", broken down by ESA WorldCover class (especially cropland) and by HAND.
  - Add a water-area time series for L, S and L+S.
- **F. Comparison:** break results down by land cover, incidence angle, HAND and water-body size. Test three hypotheses:
  - Dry sandbars are dark at L but brighter at S, so fusion should cut false water.
  - Wind roughens water at S first, so L should be more robust; the dawn ascending pass vs the dusk descending pass helps test this.
  - Flooded vegetation gives an L-band double-bounce signal.
- **G. Reproducibility:** exact granule IDs in the inventory, one command per step, pinned requirements, figure notebooks, README.
- **H. Polarimetry:** within the same granule, compare HH vs HH+HV vs full-pol.
  - L-band full-pol: C3/T3 from the GCOV terms, after the 59° fix → Pauli, H/A/α, Freeman–Durden, HH–VV coherence and phase.
  - S-band compact-pol: Stokes parameters → m, χ and m-χ.
  - Rank features by Jeffries–Matusita separability (water vs land, sand and flooded vegetation), then report ΔF1 vs the baseline.
  - Cross-check with ISRO's SARPOLTOOL.

## Validation and uncertainty

- **Reference data:**
  - Sentinel-2 MNDWI on clear days within ±2 days. Oct 2026 and Jan 2026 are the best candidates.
  - Copernicus GFM (Sentinel-1) for cloudy monsoon dates.
  - NRSC/NDEM flood maps, if published for 2026.
- **Sampling:** stratified random points by agreement among the three maps (all water / all non-water / disagree), with extra points where they disagree. Estimate accuracy and area with Stehman (2014). Use about 500 points per date.
- **Metrics:** confusion matrix, precision, recall, F1, IoU and overall accuracy. Report ΔF1 with a bootstrap 95% CI and McNemar tests (L vs L+S, S vs L+S; Foody 2004).
- **Area:** pixel count and error-adjusted area ± 95% CI (Olofsson 2014). UTM area distortion is below 0.1%; state it.
- **Checks without reference data:** false-change rate on stable pairs, ascending-vs-descending agreement two days apart, and area sensitivity to a ±1 dB threshold shift. Never invent a score where no reference exists.

## Schedule (P1 data/SAR, P2 algorithms, P3 validation and presentation)

| Day | Done when |
|---|---|
| Mon 2 Nov | Accounts and credentials set; S-band checked; first files downloaded and shrunk |
| Tue 3 | All chosen dates on the 20 m grid; QA and banding fixes done; HAND, WorldCover and JRC ready; Task A done |
| Wed 4 | L-only and S-only masks plus a simple change map over the full frame (minimum viable submission) |
| Thu 5 | Bayesian L+S, equal-information control and polarimetric features done; validation points generated |
| Fri 6 | Change classes, new-water areas and time series done; labeling finished |
| Sat 7 | All metrics, CIs and the "where fusion helps/hurts" table done. **No new features after 22:00** |
| Sun 8 | Final maps, 6–8 slides, 2–4 page technical note, README |
| Mon 9 | Full rerun in a clean environment passes; review against rubric and checklist |
| Tue 10 | Submit by about 6 PM IST |

## Pre-submission checklist

- [ ] Every output covers the full frame. The box is used only for finding scenes and for zoom insets (no clipping in any tool).
- [ ] GCOV is the only SAR input. Diagonal terms are used as intensities; the whole matrix is never treated as one image.
- [ ] Modes and channels are read from metadata, not inferred. Actual granule IDs are listed, and L/S date differences are stated.
- [ ] Unsupported three-way comparisons are stated as limitations, not faked.
- [ ] Nothing is called "flood" without independent evidence. No accuracy is reported without reference data.
- [ ] Every map shows dates, legend, CRS, resolution and source.
- [ ] Data, methods and software are cited.

## References

- ASF NISAR Data User Guide: https://nisar-docs.asf.alaska.edu (GCOV specification, data availability, PROVISIONAL known issues). GCOV product spec: Shiroma (2026), JPL D-102274 Rev F.
- ISRO Bhoonidhi NISAR page and API: https://bhoonidhi.nrsc.gov.in/NISAR/ and https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/
- Methods:
  - Thresholding: Martinis et al. (2015); Chini et al. (2017); Kittler & Illingworth (1986).
  - Accuracy and area: Olofsson et al. (2014); Stehman (2014); Foody (2004).
  - Polarimetry: Cloude & Pottier (1997); Freeman & Durden (1998); Raney et al. (2012).
  - Surface water reference: Pekel et al. (2016), JRC Global Surface Water.
