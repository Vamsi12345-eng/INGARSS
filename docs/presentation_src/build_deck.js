// Team Drishya, InGARSS 2026 YP Hackathon: NISAR L+S surface water. Default Office look (Office Theme,
// Calibri Light / Calibri, Office 2013-2022 palette), built as a structured deck from docs/technical_note.md.
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/root/.claude/skills/synced/718a0ead-907c-410d-9a85-6ab491c0aebf_7d3f56f2-fdca-478c-b8ec-332eb7e071c3/pptx/scripts/apply_theme.js");

const FIG = "/home/user/INGARSS/docs/figures";
const OUT = process.argv[2] || path.join(__dirname, "Drishya_NISAR_presentation.pptx");
const THEME = {
  name: "Office Theme", headFontFace: "Calibri Light", bodyFontFace: "Calibri",
  colors: { dk1: "000000", lt1: "FFFFFF", dk2: "44546A", lt2: "E7E6E6", accent1: "4472C4", accent2: "ED7D31",
            accent3: "A5A5A5", accent4: "FFC000", accent5: "5B9BD5", accent6: "70AD47", hlink: "0563C1", folHlink: "954F72" },
};
const HEX = { text: "000000", gray: "595959", muted: "7F7F7F", grid: "D9D9D9", accent1: "4472C4", accent2: "ED7D31",
              accent3: "A5A5A5", band1: "CFD5EA", band2: "E9EBF5", white: "FFFFFF" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in, PowerPoint's default widescreen
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "Team Drishya";
pres.company = "Team Drishya";
pres.title = "Does L+S Beat Either Band Alone? NISAR surface-water mapping";
const C = pres.SchemeColor;

// ---------- layouts (Office Theme positions, 16:9) ----------
// fresh objects per layout: pptxgenjs mutates option objects in place
const footer = () => ({ text: { text: "Team Drishya  |  InGARSS 2026 YP Hackathon", options: { x: 4.42, y: 6.95, w: 4.5, h: 0.4, fontSize: 12, color: "7F7F7F", align: "center", valign: "middle" } } });
const slideNumber = () => ({ x: 9.42, y: 6.95, w: 3, h: 0.4, fontSize: 12, color: "7F7F7F", align: "right" });
const titlePh = () => ({ placeholder: { options: { name: "title", type: "title", x: 0.917, y: 0.4, w: 11.5, h: 1.45, fontFace: THEME.headFontFace, fontSize: 40, color: C.text1, align: "left", valign: "middle" }, text: "" } });

pres.defineSlideMaster({
  title: "Title Slide", background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 1.667, y: 1.227, w: 10, h: 2.61, fontFace: THEME.headFontFace, fontSize: 54, color: C.text1, align: "center", valign: "bottom" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 1.667, y: 3.938, w: 10, h: 1.81, fontFace: THEME.bodyFontFace, fontSize: 22, color: C.text1, align: "center", valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "Title and Content", background: { color: "FFFFFF" }, slideNumber: slideNumber(),
  objects: [footer(), titlePh(),
    { placeholder: { options: { name: "body", type: "body", x: 0.917, y: 1.95, w: 11.5, h: 4.8, fontFace: THEME.bodyFontFace, fontSize: 22, color: C.text1, align: "left", valign: "top" }, text: "" } }],
});
pres.defineSlideMaster({
  title: "Title Only", background: { color: "FFFFFF" }, slideNumber: slideNumber(), objects: [footer(), titlePh()],
});
pres.defineSlideMaster({
  title: "Two Content", background: { color: "FFFFFF" }, slideNumber: slideNumber(),
  objects: [footer(), titlePh(),
    { placeholder: { options: { name: "left", type: "body", x: 0.917, y: 1.95, w: 5.6, h: 4.8, fontFace: THEME.bodyFontFace, fontSize: 20, color: C.text1, align: "left", valign: "top" }, text: "" } },
    { placeholder: { options: { name: "right", type: "body", x: 6.817, y: 1.95, w: 5.6, h: 4.8, fontFace: THEME.bodyFontFace, fontSize: 20, color: C.text1, align: "left", valign: "top" }, text: "" } }],
});

// ---------- helpers ----------
const bullets = (items, size, indentSize) => items.map((t, i) => {
  const lvl2 = typeof t === "object" && t.sub;
  const text = lvl2 ? t.sub : t;
  return { text, options: { bullet: lvl2 ? { indent: 18 } : true, indentLevel: lvl2 ? 1 : 0, fontSize: lvl2 ? size - 2 : size,
                            paraSpaceAfter: 6, breakLine: i < items.length - 1 } };
});
const heading = (text) => ({ text, options: { bold: true, fontSize: 22, color: C.accent1, breakLine: true, paraSpaceAfter: 4 } });
const tableRow = (cells, header, band, opts = {}) => cells.map((t, j) => ({
  text: t, options: { bold: header || (opts.boldFirst && j === 0), color: header ? HEX.white : HEX.text,
                      fill: { color: header ? HEX.accent1 : (band ? HEX.band1 : HEX.band2) }, fontSize: opts.fontSize || 14,
                      fontFace: THEME.bodyFontFace, valign: "middle", margin: [3, 6, 3, 6] } }));
const chartBase = {
  catAxisLabelColor: HEX.gray, valAxisLabelColor: HEX.gray, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, valGridLine: { color: HEX.grid, size: 0.75 }, catGridLine: { style: "none" },
  showLegend: true, legendPos: "b", legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: HEX.gray,
  dataLabelFontFace: "+mn-lt", dataLabelFontSize: 10, dataLabelColor: HEX.gray, titleFontFace: "+mn-lt",
  valAxisLineShow: false, catAxisLineShow: true,
};

// ---------- 1. title ----------
pres.addSection({ title: "Introduction" });
let s = pres.addSlide({ masterName: "Title Slide", sectionTitle: "Introduction" });
s.addText("Does L+S Beat Either Band Alone?", { placeholder: "title" });
s.addText([
  { text: "Surface-water mapping and change detection with NISAR L- and S-band GCOV over the Bihar Ganga floodplain, monsoon 2026", options: { breakLine: true, fontSize: 22 } },
  { text: " ", options: { breakLine: true, fontSize: 12 } },
  { text: "Team Drishya", options: { bold: true, breakLine: true, fontSize: 24 } },
  { text: "InGARSS 2026 Young Professionals Hackathon, Phase 1", options: { fontSize: 18, color: C.text1 } },
], { placeholder: "body" });
s.addNotes("Team Drishya. Our question: with NISAR imaging the same place at the same moment at two radar frequencies, is a water map from both bands measurably better than one from either band alone?");

// ---------- 2. problem ----------
s = pres.addSlide({ masterName: "Title and Content", sectionTitle: "Introduction" });
s.addText("Problem and Objective", { placeholder: "title" });
s.addText(bullets([
  "Map surface water and its change (stable water, new water, water loss) over the full NISAR frame around Bihar’s Ganga floodplain (25.5° N, 86.5° E) during the 2026 monsoon",
  "Do it three ways, using only NISAR L2 GCOV data: L-band only, S-band only and L+S combined",
  "Core question: does combining L- and S-band measurably beat either band alone?",
  "Fair comparison: one algorithm, one set of training pixels and one post-processing chain; only the input features change",
  "Every claim validated against independent Sentinel-2 data, with confidence intervals",
], 22), { placeholder: "body" });
s.addNotes("Fairness is what makes the answer credible: the three maps differ only in their input features.");

// ---------- 3. data ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Introduction" });
s.addText("Study Area and Data", { placeholder: "title" });
s.addTable([
  tableRow(["", "L-band (NASA / ASF)", "S-band (ISRO / Bhoonidhi)"], true),
  tableRow(["Product", "L2 GCOV, PROVISIONAL (calibrated)", "L2 GCOV, PROVISIONAL (12 Sep: urgent-response only)"], false, true, { boldFirst: true }),
  tableRow(["Mode and polarizations", "40+5 MHz, HH/HV, 10 m", "37 MHz, HH/HV, 10 m"], false, false, { boldFirst: true }),
  tableRow(["Joint L+S dates (UTC)", "14 Jul, 12 Sep, 18 Oct 2026", "14 Jul, 12 Sep, 18 Oct 2026 (none before 14 Jul)"], false, true, { boldFirst: true }),
  tableRow(["Looks per 20 m pixel", "about 19", "about 64"], false, false, { boldFirst: true }),
  tableRow(["Polarimetry pass", "14 Sep descending, quad-pol", "14 Sep descending, compact-pol"], false, true, { boldFirst: true }),
], { x: 0.917, y: 1.95, w: 11.5, colW: [2.9, 4.0, 4.6], border: { type: "solid", color: HEX.white, pt: 1 } });
s.addText(bullets([
  "Frame: ascending track 98, frame 14, about 250 × 250 km; common 20 m grid in UTM 45N (EPSG:32645)",
  "Supporting layers: Copernicus GLO-30 HAND and slope, ESA WorldCover 2021, JRC Global Surface Water",
  "Reference: Sentinel-2 L2A MNDWI on 18 Oct (same UTC day) and 13 Sep (5.4 h after the peak pass)",
], 18), { x: 0.917, y: 4.8, w: 11.5, h: 1.9, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("No S-band GCOV exists before 14 July 2026, so 14 July is the first date where both bands imaged the floodplain together; it is our low-water baseline.");

// ---------- 4. method: water mapping ----------
pres.addSection({ title: "Methodology" });
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Methodology" });
s.addText("Methodology: Water Mapping", { placeholder: "title" });
const steps = [
  ["Preprocess", "HH, HV backscatter averaged to 20 m; invalid samples masked"],
  ["Threshold", "Split-based Kittler–Illingworth on 5 km bimodal tiles"],
  ["Train", "Common pixels: dark (water) or bright (land) in both bands"],
  ["Classify", "Gaussian class models, EM prior, per-pixel P(water)"],
  ["Clean up", "HAND > 15 m or slope > 10° masked; 0.4 ha minimum unit"],
];
const bw = 2.0, gap = 0.375, by = 2.05, bh = 1.75;
steps.forEach(([h, t], i) => {
  const x = 0.917 + i * (bw + gap);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: by, w: bw, h: bh, rectRadius: 0.12, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: `step ${i + 1}` });
  s.addText([{ text: h, options: { bold: true, fontSize: 17, breakLine: true } }, { text: t, options: { fontSize: 13 } }],
            { x, y: by, w: bw, h: bh, color: C.background1, align: "center", valign: "middle", margin: 6, isTextBox: true, objectName: `step ${i + 1} text` });
  if (i < steps.length - 1) {
    s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.06, y: by + bh / 2 - 0.15, w: gap - 0.12, h: 0.3, fill: { color: HEX.accent3 }, line: { color: HEX.accent3 }, objectName: `arrow ${i + 1}` });
  }
});
s.addText(bullets([
  "Feature sets: L = [L-HH, L-HV]; S = [S-HH, S-HV]; L+S = all four channels (Bayesian likelihood fusion)",
  "Identical algorithm, settings, training pixels, clean-up and validation pixels for every feature set",
  "References: naive L AND S and L OR S; equal-information control = L-band at 40 m (about 4× the looks)",
  "Uncertain zone: 0.2 < P(water) < 0.8",
], 18), { x: 0.917, y: 4.1, w: 11.5, h: 2.6, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("The control answers the obvious objection that L+S simply has more data: S-band at 20 m has about 3.4 times the looks of L-band, so we give L-band about four times the looks by averaging to 40 m.");

// ---------- 5. method: change and validation ----------
s = pres.addSlide({ masterName: "Two Content", sectionTitle: "Methodology" });
s.addText("Change Detection and Validation", { placeholder: "title" });
s.addText([heading("Change detection"), ...bullets([
  "Post-classification comparison of the per-date maps",
  "Classes: stable water, new water, water loss, stable land",
  "Per-pixel confidence: P(gain) = P2 × (1 − P1)",
  "New water outside JRC persistent water (≥ 75%) = potential temporary surface inundation",
  "Gain: 14 Jul → 12 Sep; loss: 12 Sep → 18 Oct",
], 18)], { placeholder: "left" });
s.addText([heading("Validation"), ...bullets([
  "Reference: Sentinel-2 L2A MNDWI > 0, clouds masked with SCL",
  "18 Oct: 36,400 km² clear; 13 Sep: 21,900 km² clear",
  "Every map scored on identical pixels",
  "F1, precision, recall, IoU; 95% CIs from a 5 km block bootstrap",
  "McNemar tests; error-adjusted areas (Olofsson et al. 2014)",
], 18)], { placeholder: "right" });
s.addNotes("The block bootstrap resamples 5 km blocks rather than pixels, so spatial autocorrelation does not make the confidence intervals falsely narrow.");

// ---------- 6. water maps ----------
pres.addSection({ title: "Results" });
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Results: Surface-Water Maps", { placeholder: "title" });
s.addImage({ path: path.join(FIG, "fig_water_zoom.png"), x: 0.917, y: 1.9, w: 6.05, h: 4.8, altText: "Water maps around the 20 km reference box on 14 Jul, 12 Sep and 18 Oct 2026 from L-band only, S-band only and L+S" });
s.addText(bullets([
  "14 Jul: channels near low water; 2,866 km² mapped with L+S",
  "12 Sep: the Kosi–Ganga floodplain fills; 5,630 km²",
  "18 Oct: receding; L 2,759, S 2,374, L+S 2,464 km²",
  "L-band maps the most water, S-band the least",
  "Error-adjusted areas agree across methods: about 6,000 km² at the peak, 2,700 km² on 18 Oct",
], 18), { x: 7.25, y: 1.95, w: 5.17, h: 4.8, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("The big rivers look the same in every column; the differences are at the margins: shallow water, wet fields and the floodplain edges.");

// ---------- 7. accuracy ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Results: Accuracy against Sentinel-2", { placeholder: "title" });
s.addChart(pres.charts.BAR, [
  { name: "18 Oct", labels: ["L only", "S only", "L+S", "L, 4× looks", "L AND S", "L OR S"], values: [0.671, 0.672, 0.698, 0.639, 0.685, 0.660] },
  { name: "12 Sep (peak)", labels: ["L only", "S only", "L+S", "L, 4× looks", "L AND S", "L OR S"], values: [0.752, 0.774, 0.799, 0.731, 0.775, 0.752] },
], { ...chartBase, x: 0.917, y: 1.9, w: 7.6, h: 4.85, barDir: "col", barGapWidthPct: 80, chartColors: [HEX.accent1, HEX.accent2],
     showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000", valAxisMinVal: 0, valAxisMaxVal: 1, valAxisMajorUnit: 0.2,
     valAxisLabelFormatCode: "0.0", showTitle: true, title: "F1 score for water", titleFontSize: 14, titleColor: HEX.gray });
s.addText(bullets([
  "L+S is the most accurate of six maps on both dates",
  "18 Oct: F1 0.698 (95% CI 0.674–0.719) vs 0.671 (L) and 0.672 (S)",
  "12 Sep: F1 0.799 (0.777–0.817) vs 0.752 (L) and 0.774 (S)",
  "L-band with 4× the looks scores lowest",
], 18), { x: 8.75, y: 1.95, w: 3.67, h: 4.8, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("Two dates, the same answer: the fused map has the highest F1 on 18 October and at the 12 September peak.");

// ---------- 8. added value ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Added Value of Combining L- and S-band", { placeholder: "title" });
s.addChart(pres.charts.BAR, [
  { name: "18 Oct", labels: ["vs L only", "vs S only", "vs L, 4× looks", "vs L AND S", "vs L OR S"], values: [0.027, 0.026, 0.059, 0.013, 0.038] },
  { name: "12 Sep (peak)", labels: ["vs L only", "vs S only", "vs L, 4× looks", "vs L AND S", "vs L OR S"], values: [0.046, 0.024, 0.068, 0.023, 0.046] },
], { ...chartBase, x: 0.917, y: 1.9, w: 6.6, h: 4.85, barDir: "col", barGapWidthPct: 80, chartColors: [HEX.accent1, HEX.accent2],
     showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "+0.000", valAxisMinVal: 0, valAxisMaxVal: 0.08, valAxisMajorUnit: 0.02,
     valAxisLabelFormatCode: "0.00", showTitle: true, title: "F1 gain of L+S over each alternative", titleFontSize: 14, titleColor: HEX.gray });
s.addText(bullets([
  "Gains over each band have 95% CIs that exclude zero: +0.027 [+0.022, +0.033] and +0.046 [+0.041, +0.052] vs L; +0.026 and +0.024 vs S",
  "Complementary errors: L finds more water but also more false water; S is more precise but misses water; fusion keeps both strengths",
  "Not just more data: L-band with 4× the looks is worse",
  "Band choice changes the flood estimate: new water 4,501 km² (L) vs 3,616 km² (S)",
], 17), { x: 7.75, y: 1.95, w: 4.67, h: 4.8, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("McNemar tests: p below 0.001 for L+S versus each single band on both dates.");

// ---------- 9. where fusion helps ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Where Does Fusion Help?", { placeholder: "title" });
const strata = ["Cropland", "Grass", "Permanent water", "Sandbars (bare)", "HAND 0–1 m", "HAND 1–3 m", "HAND 3–10 m"];
s.addChart(pres.charts.BAR, [
  { name: "L only", labels: strata, values: [0.650, 0.262, 0.915, 0.732, 0.802, 0.625, 0.291] },
  { name: "S only", labels: strata, values: [0.622, 0.313, 0.891, 0.685, 0.768, 0.643, 0.355] },
  { name: "L+S", labels: strata, values: [0.658, 0.314, 0.923, 0.738, 0.807, 0.666, 0.344] },
], { ...chartBase, x: 0.917, y: 1.9, w: 7.9, h: 4.85, barDir: "col", barGapWidthPct: 60, chartColors: [HEX.accent1, HEX.accent2, HEX.accent3],
     showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelFontSize: 8, valAxisMinVal: 0, valAxisMaxVal: 1, valAxisMajorUnit: 0.2,
     valAxisLabelFormatCode: "0.0", catAxisLabelFontSize: 11, showTitle: true, title: "F1 by land cover and height above drainage, 18 Oct", titleFontSize: 14, titleColor: HEX.gray });
s.addText(bullets([
  "Largest gain just above the floodplain: HAND 1–3 m, F1 0.666 vs 0.625 (L) and 0.643 (S)",
  "L leads on cropland and sandbars, so “S-band fixes sandbars” is not supported",
  "S leads on grass and wetland",
  "L+S matches or beats the better band in nearly every class",
], 17), { x: 9.05, y: 1.95, w: 3.37, h: 4.8, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("One planned hypothesis did not hold: we expected S-band to clean up dry sandbars that look like water at L-band, but on sandbars S-band is the weaker band. The fused map is still the best there.");

// ---------- 10. change ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Results: Gain and Recession (L+S)", { placeholder: "title" });
s.addImage({ path: path.join(FIG, "fig_change_LS.png"), x: 0.917, y: 1.9, w: 5.1, h: 4.8, altText: "L+S change maps: gain 14 Jul to 12 Sep and loss 12 Sep to 18 Oct over the full frame and a zoom on the reference box" });
s.addText(bullets([
  "Gain, 14 Jul → 12 Sep: 3,774 km² of new water, 3,758 km² of it outside persistent water",
  "80% on cropland (3,038 km²); 79% within 1 m of the nearest drainage",
  "Loss, 12 Sep → 18 Oct: 3,273 km² receded; 2,266 km² stayed water",
], 17), { x: 6.3, y: 1.95, w: 6.12, h: 2.1, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addChart(pres.charts.LINE, [
  { name: "L only", labels: ["14 Jul", "12 Sep", "18 Oct"], values: [3650, 6773, 2759] },
  { name: "S only", labels: ["14 Jul", "12 Sep", "18 Oct"], values: [2007, 4964, 2374] },
  { name: "L+S", labels: ["14 Jul", "12 Sep", "18 Oct"], values: [2866, 5630, 2464] },
], { ...chartBase, x: 6.3, y: 4.1, w: 6.12, h: 2.65, chartColors: [HEX.accent1, HEX.accent2, HEX.accent3], lineSize: 2.25,
     lineDataSymbol: "circle", lineDataSymbolSize: 7, valAxisMinVal: 0, valAxisMaxVal: 8000, valAxisMajorUnit: 2000,
     valAxisLabelFormatCode: "#,##0", showTitle: true, title: "Mapped water area (km²)", titleFontSize: 13, titleColor: HEX.gray, legendPos: "r" });
s.addNotes("We call it new water, not flood, because we have no independent flood record to confirm it.");

// ---------- 11. polarimetry ----------
s = pres.addSlide({ masterName: "Title Only", sectionTitle: "Results" });
s.addText("Polarimetry (14 Sep, Descending)", { placeholder: "title" });
s.addImage({ path: path.join(FIG, "fig_polarimetry.png"), x: 0.917, y: 1.85, w: 11.5, h: 3.28, altText: "L-band quad-pol Pauli RGB, L-band HH-VV phase difference and S-band compact-pol m-chi RGB around the reference box on 14 Sep 2026" });
s.addText(bullets([
  "L-band quad-pol: Pauli decomposition and HH–VV phase difference",
  "59° phase calibration correction, sign verified: open water −20°, double bounce +167°",
], 16), { x: 0.917, y: 5.3, w: 5.6, h: 1.5, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addText(bullets([
  "6.1% of the window shows double bounce: candidate flooded vegetation",
  "S-band compact-pol m-χ separates rivers, vegetation and settlements",
], 16), { x: 6.817, y: 5.3, w: 5.6, h: 1.5, fontFace: THEME.bodyFontFace, color: C.text1, valign: "top" });
s.addNotes("For the GCOV HHVV term the documented 59 degree correction has to be applied with the opposite sign to the known-issues note; we checked it on open water and on bright double-bounce targets.");

// ---------- 12. limitations ----------
pres.addSection({ title: "Conclusions" });
s = pres.addSlide({ masterName: "Two Content", sectionTitle: "Conclusions" });
s.addText("Limitations and Future Work", { placeholder: "title" });
s.addText([heading("Limitations"), ...bullets([
  "Optical reference misses water under vegetation; the 18 Oct image is 19 h before the pass; 13 Sep is only 31% clear",
  "S-band only from 14 Jul; 12 Sep S-band is urgent-response; ISRO’s sample-shift flag covers 36% of the S swath",
  "20 Jun (L-band only) excluded: dry pre-monsoon fields look like water",
  "No banding correction; one frame and track",
], 17)], { placeholder: "left" });
s.addText([heading("Future work"), ...bullets([
  "Explain the 0.4 dB S−L offset inside the sample-shift flag, by land cover",
  "Incidence-angle banding correction; more dates (31 Aug, 6 Oct)",
  "Labelled sample points for cloudy dates and flooded vegetation",
  "Polarimetric features inside the classifier",
], 17)], { placeholder: "right" });

// ---------- 13. conclusions ----------
s = pres.addSlide({ masterName: "Title and Content", sectionTitle: "Conclusions" });
s.addText("Conclusions", { placeholder: "title" });
s.addText([...bullets([
  "Yes: combining L- and S-band measurably improves NISAR surface-water mapping",
  "F1 gains of +0.024 to +0.046 over the single bands, significant on both validated dates",
  "The gain comes from the second frequency, not from extra looks",
  "2026 monsoon: 3,774 km² of new water between 14 Jul and 12 Sep, mostly cropland in the low floodplain; 3,273 km² receded by 18 Oct",
  "Fully reproducible: github.com/Vamsi12345-eng/INGARSS (one command per step)",
], 22).map((r, i, a) => i === a.length - 1 ? { ...r, options: { ...r.options, breakLine: true } } : r), { text: " ", options: { breakLine: true, fontSize: 14 } },
  { text: "Thank you!  Team Drishya", options: { bold: true, fontSize: 26, color: C.accent1 } }], { placeholder: "body" });

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
