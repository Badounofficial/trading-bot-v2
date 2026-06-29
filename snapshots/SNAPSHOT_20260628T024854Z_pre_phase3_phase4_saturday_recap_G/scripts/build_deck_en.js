// Trading Bot V2 — Strategic Deck Builder (EN edition with FR-term glossing)
// Style: Midnight Quant. Dark backgrounds, gold accent, P&L green/red, cyan data, purple crypto accent.
// Output: /Users/mindcompletionbody/Desktop/trading-bot-v2/Trading_Bot_V2_Strategic_Deck_EN.pptx
//
// Run: NODE_PATH=~/.npm-global/lib/node_modules node scripts/build_deck_en.js

const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333" x 7.5"
pres.author = "Trading Bot V2 Project";
pres.title = "Trading Bot V2 — Strategic Overview";

const W = 13.333, H = 7.5;

// ----- Palette ----------------------------------------------------------------
const C = {
  bg:        "0A0E1A", // near-black deep navy
  bgAlt:     "0F1422", // slightly lighter for variety
  card:      "161B28",
  cardAlt:   "1B2233",
  border:    "2A3245",
  gold:      "D4AF37",
  goldDim:   "8C7327",
  cyan:      "22D3EE",
  green:     "10B981",
  greenDim:  "065F46",
  red:       "EF4444",
  redDim:    "7F1D1D",
  purple:    "A78BFA",
  text:      "F8FAFC",
  textMid:   "CBD5E1",
  textMuted: "94A3B8",
  textDim:   "64748B",
};

const FONT_H = "Helvetica Neue";
const FONT_B = "Helvetica";

// ----- Helpers ----------------------------------------------------------------
function addBg(slide, color = C.bg) {
  slide.background = { color };
}

// Slim gold rule on the left edge of content slides (visual motif)
function addLeftAccent(slide) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0.6, w: 0.05, h: H - 1.2,
    fill: { color: C.gold }, line: { color: C.gold, width: 0 },
  });
}

function addFooter(slide, num, total) {
  // Footer rule + caption
  slide.addShape(pres.shapes.LINE, {
    x: 0.6, y: H - 0.45, w: W - 1.2, h: 0,
    line: { color: C.border, width: 0.75 },
  });
  slide.addText("TRADING BOT V2  ·  STRATEGIC DECK", {
    x: 0.6, y: H - 0.4, w: 6, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted,
    charSpacing: 4, margin: 0,
  });
  slide.addText(`${num} / ${total}`, {
    x: W - 1.6, y: H - 0.4, w: 1, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted,
    align: "right", margin: 0,
  });
}

function addSlideTitle(slide, eyebrow, title) {
  slide.addText(eyebrow, {
    x: 0.6, y: 0.45, w: 10, h: 0.3,
    fontFace: FONT_B, fontSize: 11, color: C.gold,
    bold: true, charSpacing: 6, margin: 0,
  });
  slide.addText(title, {
    x: 0.6, y: 0.78, w: W - 1.2, h: 0.7,
    fontFace: FONT_H, fontSize: 28, color: C.text,
    bold: true, margin: 0,
  });
}

// Card with subtle shadow + thin top border in accent color
function addCard(slide, x, y, w, h, accent = C.gold, opts = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opts.fill || C.card },
    line: { color: C.border, width: 0.5 },
  });
  // top accent strip
  if (accent) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w, h: 0.05,
      fill: { color: accent }, line: { color: accent, width: 0 },
    });
  }
}

const TOTAL = 16;

// =============================================================================
// SLIDE 1 — TITLE
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);

  // Background motif: a thin gold rule on left, a faint cyan rule on right
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 0.04, h: H - 1.6,
    fill: { color: C.gold }, line: { color: C.gold, width: 0 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: W - 0.7, y: 1.0, w: 0.02, h: H - 1.6,
    fill: { color: C.cyan, transparency: 60 }, line: { color: C.cyan, width: 0 },
  });

  s.addText("ALGORITHMIC TRADING  ·  CRYPTO PERPETUALS  ·  MAY 2026", {
    x: 0.9, y: 1.4, w: 11, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 8, margin: 0,
  });

  s.addText("Trading Bot V2", {
    x: 0.85, y: 2.0, w: 11.5, h: 1.2,
    fontFace: FONT_H, fontSize: 64, color: C.text,
    bold: true, margin: 0,
  });

  s.addText("Strategic Overview", {
    x: 0.85, y: 3.2, w: 11.5, h: 0.7,
    fontFace: FONT_H, fontSize: 32, color: C.cyan, margin: 0,
  });

  s.addText("ICC Methodology Applied to 8 Crypto Assets  ·  Hyperliquid + Kraken", {
    x: 0.9, y: 4.1, w: 11.5, h: 0.4,
    fontFace: FONT_B, fontSize: 16, color: C.textMid, margin: 0,
  });

  // Bottom block: 3 KPI hero strip
  const yK = 5.5, hK = 1.2;
  const kpi = [
    { v: "49.5%", l: "WR · OOS+FRICTION · 8 MAJORS", col: C.green },
    { v: "2.09",  l: "PF · WALK-FORWARD AVG",        col: C.cyan  },
    { v: "0.97",  l: "SHARPE ANN. · OOS+FRICTION",   col: C.gold  },
  ];
  const colW = 3.6, colGap = 0.4;
  const totalW = kpi.length * colW + (kpi.length - 1) * colGap;
  const startX = (W - totalW) / 2;
  kpi.forEach((k, i) => {
    const x = startX + i * (colW + colGap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: yK, w: colW, h: hK,
      fill: { color: C.card }, line: { color: C.border, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: yK, w: 0.05, h: hK,
      fill: { color: k.col }, line: { color: k.col, width: 0 },
    });
    s.addText(k.v, {
      x: x + 0.2, y: yK + 0.1, w: colW - 0.4, h: 0.6,
      fontFace: FONT_H, fontSize: 32, color: k.col, bold: true, margin: 0,
    });
    s.addText(k.l, {
      x: x + 0.2, y: yK + 0.7, w: colW - 0.4, h: 0.4,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted,
      charSpacing: 4, margin: 0,
    });
  });

  s.addText("Confidential  ·  Internal Use Only", {
    x: 0.9, y: H - 0.4, w: 11.5, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted,
    charSpacing: 6, margin: 0,
  });
}

// =============================================================================
// SLIDE 2 — EXECUTIVE SUMMARY
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "01  ·  EXECUTIVE SUMMARY", "Where the project stands today");
  addFooter(s, 2, TOTAL);

  // Mandatory 4-qualifier methodology line (per Directive #2)
  s.addText("METHODO walk-forward OOS · FRICTION fees+slippage+funding · WINDOW 2024–25 bull + 2022–23 bear · REGIME mixed", {
    x: 0.9, y: 1.55, w: W - 1.8, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.cyan, italic: true, charSpacing: 2, margin: 0,
  });

  // 2x2 grid of stat cards
  const items = [
    {
      eyebrow: "VALIDATED METHODOLOGY",
      stat: "ICC + SMC",
      body: "Indication–Correction–Continuation pipeline (Daily / H4 / H1). 94/94 unit tests green. No-lookahead enforced.",
      accent: C.gold,
    },
    {
      eyebrow: "OOS WALK-FORWARD + FRICTION",
      stat: "PF 1.64–2.54  ·  Sharpe 0.84–1.11",
      body: "309 trades, 8 majors. Bull '24–'25: PF 1.64, WR 49.1%, ΣPnL +89pp. Bear '22–'23: PF 2.54, WR 50.0%, ΣPnL +127pp. In-sample headline (+501pp) was −82% optimistic.",
      accent: C.green,
    },
    {
      eyebrow: "REGULATORY CONTEXT",
      stat: "MiCA  ·  1 July 2026",
      body: "Proprietary bot: no CASP licence required. Signals or copy-trading for third parties: licence mandatory. Flat Tax (PFU) 31.4% in FR; DAC8 (EU directive on crypto reporting) auto-reporting active.",
      accent: C.cyan,
    },
    {
      eyebrow: "PROJECTED NET P&L (MEDIAN)",
      stat: "+$11k → +$320k / yr",
      body: "Phase actual: $50k @ ~15–20 % net ≈ +$8–11k. End-of-build (+ funding capture): ≈ +$15k. Optimized multi-strategy + community: +$70k → +$320k.",
      accent: C.purple,
    },
  ];

  const gx = 0.9, gy = 1.95;
  const cw = 5.85, ch = 2.1, gap = 0.2;
  items.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = gx + col * (cw + gap), y = gy + row * (ch + gap);
    addCard(s, x, y, cw, ch, it.accent);
    s.addText(it.eyebrow, {
      x: x + 0.3, y: y + 0.2, w: cw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 10, color: it.accent,
      bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(it.stat, {
      x: x + 0.3, y: y + 0.55, w: cw - 0.6, h: 0.7,
      fontFace: FONT_H, fontSize: 26, color: C.text, bold: true, margin: 0,
    });
    s.addText(it.body, {
      x: x + 0.3, y: y + 1.25, w: cw - 0.6, h: 0.9,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
      paraSpaceAfter: 3,
    });
  });

  s.addText("Source: internal backtest commit fbf497a · ESMA MiCA · DGFiP (French Tax Administration) / Hagnere Patrimoine 2026", {
    x: 0.9, y: 6.55, w: 11.5, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted,
    italic: true, margin: 0,
  });
}

// =============================================================================
// SLIDE 3 — STRATEGY OVERVIEW (3-TF pipeline)
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "02  ·  STRATEGY OVERVIEW", "ICC multi-timeframe cascade");
  addFooter(s, 3, TOTAL);

  // Three TF boxes horizontally
  const boxes = [
    { tf: "DAILY", role: "BIAS",        body: "Direction master\nBULL / BEAR / NEUTRAL\nfrom unbroken structure", accent: C.gold,   },
    { tf: "H4",    role: "INDICATION",  body: "CHoCH break: NEW_HIGH / NEW_LOW\nValid Order Block detected\nImpulse + Fibo geometry", accent: C.cyan,   },
    { tf: "H1",    role: "ENTRY",       body: "Correction tracking (Path A + B)\nBody close past micro LH / HL\nStructural SL & TP", accent: C.purple, },
  ];
  const bw = 3.7, bh = 2.6, gy = 1.9;
  const totalW = boxes.length * bw + (boxes.length - 1) * 0.5;
  const sx = (W - totalW) / 2;
  boxes.forEach((b, i) => {
    const x = sx + i * (bw + 0.5);
    addCard(s, x, gy, bw, bh, b.accent);
    s.addText(b.tf, {
      x: x + 0.3, y: gy + 0.25, w: bw - 0.6, h: 0.5,
      fontFace: FONT_H, fontSize: 28, color: b.accent, bold: true, margin: 0,
    });
    s.addText(b.role, {
      x: x + 0.3, y: gy + 0.85, w: bw - 0.6, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.text,
      bold: true, charSpacing: 6, margin: 0,
    });
    s.addText(b.body, {
      x: x + 0.3, y: gy + 1.3, w: bw - 0.6, h: 1.2,
      fontFace: FONT_B, fontSize: 12, color: C.textMid, margin: 0,
    });

    // Chevron arrow between boxes
    if (i < boxes.length - 1) {
      const ax = x + bw + 0.05, ay = gy + bh / 2 - 0.35;
      s.addText("▶", {
        x: ax, y: ay, w: 0.4, h: 0.6,
        fontFace: FONT_H, fontSize: 22, color: C.gold,
        bold: true, align: "center", valign: "middle", margin: 0,
      });
    }
  });

  // Bottom: state machine flow text
  const yFlow = 4.8;
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: yFlow, w: W - 1.8, h: 1.6,
    fill: { color: C.cardAlt }, line: { color: C.border, width: 0.5 },
  });
  s.addText("STATE MACHINE", {
    x: 1.1, y: yFlow + 0.15, w: 10, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.gold, bold: true, charSpacing: 5, margin: 0,
  });
  const states = ["SCANNING", "INDICATION", "CORRECTION", "READY", "IN_TRADE", "COOLDOWN"];
  const sw = (W - 2.0) / states.length;
  states.forEach((st, i) => {
    const x = 1.0 + i * sw;
    s.addText(st, {
      x: x, y: yFlow + 0.6, w: sw, h: 0.5,
      fontFace: FONT_H, fontSize: 14, color: C.text, bold: true,
      align: "center", margin: 0,
    });
    if (i < states.length - 1) {
      s.addText("›", {
        x: x + sw - 0.15, y: yFlow + 0.55, w: 0.3, h: 0.5,
        fontFace: FONT_H, fontSize: 22, color: C.gold,
        align: "center", margin: 0,
      });
    }
  });
  s.addText("Entry triggers on body-close past the H1 micro-structure that formed during the correction phase. " +
            "SL is anchored on the previous H1 HL/LH close; TP is the nearest opposite OB on H4/Daily (RR ≥ 2.5) or 1:3 measured-move fallback.", {
    x: 1.1, y: yFlow + 1.1, w: W - 2.2, h: 0.45,
    fontFace: FONT_B, fontSize: 11, color: C.textMuted, margin: 0,
  });
}

// =============================================================================
// SLIDE 4 — TECHNICAL ARCHITECTURE
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "03  ·  TECHNICAL ARCHITECTURE", "Stack, data flow, testing posture");
  addFooter(s, 4, TOTAL);

  // Left col: stack
  const lx = 0.9, ly = 1.7, lw = 5.6, lh = 5.0;
  addCard(s, lx, ly, lw, lh, C.cyan);
  s.addText("STACK", {
    x: lx + 0.3, y: ly + 0.2, w: lw - 0.6, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.cyan, bold: true, charSpacing: 5, margin: 0,
  });
  const stackRows = [
    { k: "Language",    v: "Python 3.x" },
    { k: "Core",        v: "pandas · numpy · pyarrow · ccxt" },
    { k: "Strategies",  v: "icc_structure / icc_orderblocks / icc_cycle" },
    { k: "Backtest",    v: "backtest/engine.py + backtest/directional_engine.py" },
    { k: "Walk-forward", v: "strategies/walkforward_icc.py" },
    { k: "Paper",       v: "paper_trading/order_simulator.py" },
    { k: "Tests",       v: "pytest · 94/94 green" },
    { k: "Storage",     v: "parquet cache (Daily / H4 / H1)" },
    { k: "VCS",         v: "git · ~10 sessions logged in docs/RECAPS/" },
  ];
  const rowH = 0.42;
  stackRows.forEach((r, i) => {
    const y = ly + 0.7 + i * rowH;
    s.addText(r.k.toUpperCase(), {
      x: lx + 0.3, y, w: 1.7, h: rowH,
      fontFace: FONT_B, fontSize: 10, color: C.textMuted,
      charSpacing: 3, margin: 0,
    });
    s.addText(r.v, {
      x: lx + 2.0, y, w: lw - 2.2, h: rowH,
      fontFace: FONT_B, fontSize: 12, color: C.text, margin: 0,
    });
  });

  // Right col: dataflow boxes vertically
  const rx = 6.9, ry = 1.7, rw = 5.6;
  const flow = [
    { t: "EXCHANGES",       sub: "Hyperliquid (perp + funding)  ·  Kraken (spot OHLC)", c: C.purple },
    { t: "DATA LAYER",      sub: "fetch_multi_tf / fetch_universe / parse_kraken_zip",   c: C.cyan },
    { t: "STRATEGY LAYER",  sub: "ICC swing  ·  trend  ·  funding  ·  MR  ·  XSec",      c: C.gold },
    { t: "BACKTEST + WF",   sub: "Walk-forward 12m / 6m / 3m  ·  per-asset metrics",    c: C.green },
    { t: "PAPER TRADING",   sub: "Local simulator · Phase 1 (no broker, zero capital)",  c: C.textMid },
  ];
  const fh = 0.85, fGap = 0.15;
  flow.forEach((f, i) => {
    const y = ry + i * (fh + fGap);
    addCard(s, rx, y, rw, fh, f.c);
    s.addText(f.t, {
      x: rx + 0.3, y: y + 0.12, w: rw - 0.6, h: 0.35,
      fontFace: FONT_H, fontSize: 14, color: f.c, bold: true, margin: 0,
    });
    s.addText(f.sub, {
      x: rx + 0.3, y: y + 0.45, w: rw - 0.6, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 5 — BACKTEST PERFORMANCE (OOS WALK-FORWARD + FRICTION)
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "04  ·  BACKTEST PERFORMANCE", "OOS walk-forward · friction applied · 2 regimes");
  addFooter(s, 5, TOTAL);

  // Mandatory 4-qualifier line
  s.addText("METHODO walk-forward (12m/6m/3m) · FRICTION fees 4.5bps×2 + tiered slippage + funding · WINDOW 2024–25 bull + 2022–23 bear · REGIME both", {
    x: 0.9, y: 1.55, w: W - 1.8, h: 0.22,
    fontFace: FONT_B, fontSize: 9, color: C.cyan, italic: true, charSpacing: 2, margin: 0,
  });

  // Headline 4 KPIs at top — OOS+friction averages
  const kpis = [
    { l: "OOS TRADES (BOTH WINDOWS)",  v: "309",       c: C.gold },
    { l: "WR · WEIGHTED OOS",          v: "49.5%",     c: C.green },
    { l: "PF · WEIGHTED OOS",          v: "2.09",      c: C.cyan },
    { l: "SHARPE ANN. · OOS+FRICTION", v: "0.97",      c: C.purple },
  ];
  const kw = 2.7, kh = 0.95, kgap = 0.25, ky = 1.85;
  const ktw = kpis.length * kw + (kpis.length - 1) * kgap;
  const ksx = (W - ktw) / 2;
  kpis.forEach((k, i) => {
    const x = ksx + i * (kw + kgap);
    addCard(s, x, ky, kw, kh, k.c);
    s.addText(k.v, {
      x: x + 0.2, y: ky + 0.1, w: kw - 0.4, h: 0.5,
      fontFace: FONT_H, fontSize: 24, color: k.c, bold: true, margin: 0,
    });
    s.addText(k.l, {
      x: x + 0.2, y: ky + 0.6, w: kw - 0.4, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 4, margin: 0,
    });
  });

  // In-sample vs OOS+friction comparison table
  const tx = 0.9, ty = 3.1, tw = W - 1.8;
  const cols = ["DATASET", "METHODO", "FRICT.", "TRD", "WR", "PF", "Σ PNL pp", "DD", "SHARPE", "VERDICT"];
  const rowsT = [
    [
      { text: "2024–25 (bull)", options: { bold: true, color: C.text } },
      { text: "In-sample full-period", options: { color: C.textMid } },
      { text: "OFF", options: { color: C.red, bold: true } },
      { text: "332", options: { color: C.text } },
      { text: "60.5%", options: { color: C.green } },
      { text: "3.84",  options: { color: C.green } },
      { text: "+501",  options: { color: C.green } },
      { text: "~7%",   options: { color: C.text } },
      { text: "—",     options: { color: C.textDim } },
      { text: "INVALID", options: { bold: true, color: C.red } },
    ],
    [
      { text: "2024–25 (bull)", options: { bold: true, color: C.text } },
      { text: "Walk-forward OOS", options: { color: C.textMid } },
      { text: "ON",  options: { color: C.green, bold: true } },
      { text: "167", options: { color: C.text } },
      { text: "49.1%", options: { color: C.gold } },
      { text: "1.64",  options: { color: C.gold } },
      { text: "+89",   options: { color: C.gold } },
      { text: "12.7%", options: { color: C.gold } },
      { text: "0.84",  options: { color: C.gold } },
      { text: "MARGINAL", options: { bold: true, color: C.gold } },
    ],
    [
      { text: "2022–23 (bear→rec.)", options: { bold: true, color: C.text } },
      { text: "Walk-forward OOS",    options: { color: C.textMid } },
      { text: "ON",  options: { color: C.green, bold: true } },
      { text: "142", options: { color: C.text } },
      { text: "50.0%", options: { color: C.green } },
      { text: "2.54",  options: { color: C.green } },
      { text: "+127",  options: { color: C.green } },
      { text: "7.3%",  options: { color: C.green } },
      { text: "1.11",  options: { color: C.green } },
      { text: "VALID",   options: { bold: true, color: C.green } },
    ],
  ];
  const headerRow = cols.map(c => ({
    text: c,
    options: { bold: true, color: "0A0E1A", fontFace: FONT_B, fontSize: 10,
               fill: { color: C.gold }, charSpacing: 3 },
  }));
  s.addTable([headerRow, ...rowsT], {
    x: tx, y: ty, w: tw,
    colW: [1.9, 2.2, 0.7, 0.7, 0.9, 0.7, 1.0, 0.9, 1.0, 1.5333],
    fontFace: FONT_B, fontSize: 11,
    border: { type: "solid", pt: 0.5, color: C.border },
    fill: { color: C.card },
    rowH: 0.45,
  });

  // Insight callout — pulled up
  const cy = 5.05;
  addCard(s, 0.9, cy, W - 1.8, 1.4, C.gold, { fill: C.cardAlt });
  s.addText([
    { text: "INSIGHT  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "The in-sample headline (+501 pp, PF 3.84) was −82 % optimistic. ", options: { color: C.text } },
    { text: "OOS + friction collapses the bull-tape PnL to +89 pp / PF 1.64 / Sharpe 0.84. The bear-recovery 2022–23 window actually performs BETTER (PF 2.54, Sharpe 1.11), suggesting the strategy survives a stress regime — but 4 of 8 assets lose money on the bull tape (BTC, ADA, DOT, LINK). Asset filtering required.",
      options: { color: C.textMid } },
  ], {
    x: 1.1, y: cy + 0.18, w: W - 2.2, h: 1.15,
    fontFace: FONT_B, fontSize: 12, margin: 0,
  });
}

// =============================================================================
// SLIDE 6 — ASSET UNIVERSE (8 cards 2x4)
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "05  ·  ASSET UNIVERSE", "8 majors, aligned Daily/H4/H1 over 2024–2025");
  addFooter(s, 6, TOTAL);

  const assets = [
    { name: "BTC",  pnl: "+25.7",  wr: "52.9", n: "34", c: C.gold },
    { name: "ETH",  pnl: "+89.3",  wr: "79.5", n: "39", c: C.green },
    { name: "SOL",  pnl: "+72.2",  wr: "48.8", n: "43", c: C.purple },
    { name: "ADA",  pnl: "+34.6",  wr: "51.1", n: "47", c: C.cyan },
    { name: "AVAX", pnl: "+101.9", wr: "69.8", n: "53", c: C.green },
    { name: "DOT",  pnl: "+34.4",  wr: "57.1", n: "28", c: C.gold },
    { name: "LINK", pnl: "+89.1",  wr: "62.3", n: "53", c: C.cyan },
    { name: "LTC",  pnl: "+53.9",  wr: "60.0", n: "35", c: C.purple },
  ];
  const gx0 = 0.9, gy0 = 1.7;
  const cw = 2.9, ch = 1.95, hg = 0.18, vg = 0.18;
  assets.forEach((a, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = gx0 + col * (cw + hg), y = gy0 + row * (ch + vg);
    addCard(s, x, y, cw, ch, a.c);
    s.addText(a.name, {
      x: x + 0.25, y: y + 0.2, w: cw - 0.5, h: 0.45,
      fontFace: FONT_H, fontSize: 22, color: a.c, bold: true, margin: 0,
    });
    s.addText("PNL", {
      x: x + 0.25, y: y + 0.75, w: 1.0, h: 0.22,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(`${a.pnl}%`, {
      x: x + 0.25, y: y + 0.95, w: cw - 0.5, h: 0.4,
      fontFace: FONT_H, fontSize: 18, color: C.green, bold: true, margin: 0,
    });
    // mini metrics row
    s.addText([
      { text: "WR ", options: { color: C.textMuted } },
      { text: `${a.wr}%`, options: { color: C.text, bold: true } },
      { text: "   N ", options: { color: C.textMuted } },
      { text: a.n, options: { color: C.text, bold: true } },
    ], {
      x: x + 0.25, y: y + 1.45, w: cw - 0.5, h: 0.35,
      fontFace: FONT_B, fontSize: 11, margin: 0,
    });
  });

  // Footer note for excluded
  const yN = 6.0;
  addCard(s, 0.9, yN, W - 1.8, 0.85, C.red);
  s.addText([
    { text: "DOGE — EXCLUDED  ·  ", options: { bold: true, color: C.red, charSpacing: 4 } },
    { text: "Insufficient coverage in cache (1h: ~30 days only, 4h: ~4 months) for a 2-year aligned window. Funding-rate data on Hyperliquid available for BTC/ETH/SOL — used in the funding_capture branch only.",
      options: { color: C.textMid } },
  ], {
    x: 1.1, y: yN + 0.18, w: W - 2.2, h: 0.5,
    fontFace: FONT_B, fontSize: 11, margin: 0,
  });
}

// =============================================================================
// SLIDE 7 — SWOT
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "06  ·  SWOT", "Honest internal/external assessment");
  addFooter(s, 7, TOTAL);

  const quad = [
    { t: "STRENGTHS", c: C.green, items: [
        "Rigor: unit tests per ICC concept, anti-lookahead, walk-forward native",
        "In-sample edge: PF 3.84, WR 60.5%, +501 pp over 2 years / 8 majors",
        "Honest analytics: V2 fix tested, measured, rejected, documented",
        "Best-in-class venues: Hyperliquid (44% perp-DEX share) + Kraken",
        "Diversified strategy bench (ICC, trend, funding, MR, momentum XSec)",
    ]},
    { t: "WEAKNESSES", c: C.red, items: [
        "No live nor real-time paper yet — all backtest-only",
        "Friction (fees, slippage) under-modelled in ICC pipeline",
        "No portfolio-level sizing or cross-asset risk control",
        "INTRADAY / SCALPING modes advertised in enum but not coded",
        "Only 2 years of aligned 4h/1h data on the 8 majors",
    ]},
    { t: "OPPORTUNITIES", c: C.cyan, items: [
        "Hyperliquid in rapid ascent: 36% → 44% perp-DEX share in 4 mo",
        "Open vertical: no real end-to-end ICC bot in Python on the market",
        "Funding arb on Hyperliquid: net APR 3–12% majors, 20–60%+ mid-caps",
        "Crypto quant funds: ~48% avg return, Sharpe 1.6 (sqmagazine)",
        "SMC community size: 15k+ active members on commercial alts",
    ]},
    { t: "THREATS", c: C.gold, items: [
        "MiCA effective 1 July 2026 — CASP licence if managing 3rd-party capital",
        "Exchange / smart-contract risk on Hyperliquid (young L1)",
        "Regime change: 2026–2027 bear/rangy would compress edge",
        "Crypto tail risk: flash crashes, stablecoin breaks, exploits",
        "Flat Tax (PFU) @ 31.4% (2026); Non-commercial earnings (BNC) requalification if trading is intensive",
    ]},
  ];
  const gx = 0.9, gy = 1.65;
  const cw = 5.85, ch = 2.4, hg = 0.3, vg = 0.2;
  quad.forEach((q, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = gx + col * (cw + hg), y = gy + row * (ch + vg);
    addCard(s, x, y, cw, ch, q.c);
    s.addText(q.t, {
      x: x + 0.3, y: y + 0.12, w: cw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 12, color: q.c, bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(
      q.items.map((it, idx) => ({
        text: it,
        options: { bullet: { code: "25A0" }, color: C.textMid,
                   breakLine: idx < q.items.length - 1 },
      })),
      { x: x + 0.35, y: y + 0.5, w: cw - 0.7, h: ch - 0.6,
        fontFace: FONT_B, fontSize: 10.5, margin: 0, paraSpaceAfter: 3 }
    );
  });
}

// =============================================================================
// SLIDE 8 — MARKET OPPORTUNITY
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "07  ·  MARKET OPPORTUNITY", "Where the wallet is going in 2026");
  addFooter(s, 8, TOTAL);

  // 3 hero stats top row
  const stats = [
    { v: "$21.8 B",  l: "HYPERLIQUID 24H VOLUME",      c: C.cyan,   src: "yellow.com 2026" },
    { v: "44%",      l: "HYPERLIQUID PERP-DEX SHARE",  c: C.purple, src: "yellow.com 2026" },
    { v: "48% / 1.6", l: "AVG CRYPTO QUANT FUND 2025", c: C.green, src: "return % / Sharpe — sqmagazine 2026" },
  ];
  const sw = 4.05, sh = 1.2, sg = 0.2, sy = 1.7;
  const stw = stats.length * sw + (stats.length - 1) * sg;
  const ssx = (W - stw) / 2;
  stats.forEach((st, i) => {
    const x = ssx + i * (sw + sg);
    addCard(s, x, sy, sw, sh, st.c);
    s.addText(st.v, {
      x: x + 0.25, y: sy + 0.1, w: sw - 0.5, h: 0.55,
      fontFace: FONT_H, fontSize: 28, color: st.c, bold: true, margin: 0,
    });
    s.addText(st.l, {
      x: x + 0.25, y: sy + 0.7, w: sw - 0.5, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 4, margin: 0,
    });
    s.addText(st.src, {
      x: x + 0.25, y: sy + 0.95, w: sw - 0.5, h: 0.2,
      fontFace: FONT_B, fontSize: 8, color: C.textDim, italic: true, margin: 0,
    });
  });

  // Bar chart: Hyperliquid perp-DEX share growth
  const chartData = [{
    name: "Hyperliquid Perp-DEX Share %",
    labels: ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026"],
    values: [36.4, 39, 42, 44],
  }];
  s.addChart(pres.charts.BAR, chartData, {
    x: 0.9, y: 3.2, w: 6.0, h: 3.5,
    barDir: "col",
    chartColors: [C.cyan],
    chartArea: { fill: { color: C.card }, border: { color: C.border, pt: 0.5 } },
    plotArea: { fill: { color: C.card } },
    catAxisLabelColor: C.textMid,
    catAxisLabelFontFace: FONT_B,
    catAxisLabelFontSize: 11,
    valAxisLabelColor: C.textMid,
    valAxisLabelFontFace: FONT_B,
    valAxisLabelFontSize: 10,
    valGridLine: { color: C.border, size: 0.5 },
    catGridLine: { style: "none" },
    showValue: true,
    dataLabelPosition: "outEnd",
    dataLabelColor: C.cyan,
    dataLabelFontFace: FONT_B,
    dataLabelFontSize: 11,
    showTitle: true,
    title: "Hyperliquid market share gain — 2026",
    titleColor: C.gold,
    titleFontFace: FONT_H,
    titleFontSize: 14,
    titleBold: true,
    showLegend: false,
    barGapWidthPct: 60,
  });

  // Right column: 4 mini-stats from competitive landscape
  const rx = 7.2, ry = 3.2;
  const rows = [
    { k: "Crypto bot subscription mkt",  v: "12-25% avg ann. returns (3Commas / Cryptohopper top users)" },
    { k: "Funding arb net APR",          v: "3–12% BTC/ETH · 20–60% mid-caps · 30–80% long-tail" },
    { k: "Retail bot failure rate",      v: "~95% of AI retail bots lose money within 90 days" },
    { k: "Hyperliquid fees",             v: "0.015% maker  ·  0.045% taker (best-in-class)" },
    { k: "SMC commercial bot audience",  v: "SMRT Algo: 15 000+ active members across asset classes" },
  ];
  addCard(s, rx, ry, 5.3, 3.5, C.gold);
  s.addText("MARKET DATA POINTS", {
    x: rx + 0.3, y: ry + 0.15, w: 5, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.gold, bold: true, charSpacing: 5, margin: 0,
  });
  rows.forEach((r, i) => {
    const y = ry + 0.55 + i * 0.56;
    s.addText(r.k.toUpperCase(), {
      x: rx + 0.3, y, w: 5, h: 0.22,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(r.v, {
      x: rx + 0.3, y: y + 0.22, w: 5, h: 0.32,
      fontFace: FONT_B, fontSize: 11, color: C.text, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 9 — COMPETITIVE LANDSCAPE
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "08  ·  COMPETITIVE LANDSCAPE", "Where Trading Bot V2 fits in the 2026 ecosystem");
  addFooter(s, 9, TOTAL);

  const head = ["CATEGORY", "PLAYER", "MODEL", "PRICING", "EDGE / NICHE"];
  const rows = [
    ["TradingView indicators", "LuxAlgo SMC", "Free freemium", "$0 → $40/mo", "Visual only, no execution"],
    ["TV indicators paid",     "Zeiierman SMC, SMC Sniper Pro", "Subscription", "$30–80/mo", "Closed-source, visual"],
    ["All-in-one bot SaaS",    "3Commas · Cryptohopper · WunderTrading", "SaaS",      "$15–100/mo",  "Grid/DCA dominant, AI marketed"],
    ["SMC bot SaaS",           "SMRT Algo",                                "SaaS+TV",   "$15–30/mo",   "15k+ members, broad asset coverage"],
    ["Copy-trading exchange",  "Binance · Bybit · OKX Copy",               "Native",    "Spread + fees", "Massive distribution"],
    ["Copy-trading SaaS",      "Finestel · Stoic.ai",                      "Subscription + perf", "Variable", "Pro multi-account mgmt"],
    ["Open-source Py",         "joshyattridge/smart-money-concepts",       "Library",   "Free",        "Building block, not a bot"],
    [
      { text: "Trading Bot V2", options: { bold: true, color: C.gold } },
      { text: "(this project)", options: { color: C.gold } },
      { text: "End-to-end Py", options: { color: C.gold } },
      { text: "TBD",           options: { color: C.gold } },
      { text: "Backtest-rigorous ICC, transparent, dual venue (CEX + DEX)", options: { color: C.gold, italic: true } },
    ],
  ];
  const headRow = head.map(c => ({
    text: c,
    options: { bold: true, color: "0A0E1A", fill: { color: C.gold }, charSpacing: 4 },
  }));
  s.addTable([headRow, ...rows], {
    x: 0.9, y: 1.7, w: W - 1.8,
    colW: [2.3, 2.7, 1.7, 1.6, 3.2333],
    fontFace: FONT_B, fontSize: 11,
    border: { type: "solid", pt: 0.5, color: C.border },
    fill: { color: C.card },
    color: C.textMid,
    rowH: 0.48,
  });

  const yC = 6.0;
  addCard(s, 0.9, yC, W - 1.8, 0.85, C.gold, { fill: C.cardAlt });
  s.addText([
    { text: "POSITIONING  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "An open, reproducible, ICC-faithful Python stack with real backtest + walk-forward is a narrow but genuinely empty market segment. Most competitors are visual-only or closed SaaS.",
      options: { color: C.text } },
  ], {
    x: 1.1, y: yC + 0.18, w: W - 2.2, h: 0.55,
    fontFace: FONT_B, fontSize: 12, margin: 0,
  });
}

// =============================================================================
// SLIDE 10 — REGULATORY & TAX
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "09  ·  REGULATORY & TAX", "MiCA in force, DAC8 live, Flat Tax (PFU) at 31.4%");
  addFooter(s, 10, TOTAL);

  const cards = [
    {
      tag: "MiCA",
      head: "EU CRYPTO REGULATION",
      sub: "Effective 1 July 2026",
      body: [
        "Proprietary bot (own capital) → no licence required.",
        "Signals exec'd for third parties / managed portfolios → CASP licence mandatory.",
        "ESMA Feb-2026 briefing: HFT / algo crypto must keep detailed order logs.",
      ],
      c: C.cyan,
    },
    {
      tag: "PFU",
      head: "FLAT TAX FR 2026",
      sub: "31.4% (12.8% IT + 18.6% SS)",
      body: [
        "Capital gains > €305 / year → declared via Form 2086 (FR capital-gains declaration).",
        "Option for progressive Income Tax (IR) scale if more favorable.",
        "Heavy bot activity → Non-commercial earnings (BNC) requalification risk (worse than PFU flat tax).",
      ],
      c: C.gold,
    },
    {
      tag: "DAC8",
      head: "AUTOMATIC REPORTING",
      sub: "Live since 1 January 2026",
      body: [
        "EU directive on crypto reporting — crypto platforms auto-transmit history to DGFiP (French Tax Administration).",
        "Effective end of grey-zone declaration across EU jurisdictions.",
        "Discipline required: keep clean trade logs and reconciliations.",
      ],
      c: C.purple,
    },
  ];
  const cw = 4.05, ch = 4.2, gap = 0.2, cy = 1.7;
  const totalW = cards.length * cw + (cards.length - 1) * gap;
  const csx = (W - totalW) / 2;
  cards.forEach((c, i) => {
    const x = csx + i * (cw + gap);
    addCard(s, x, cy, cw, ch, c.c);
    s.addText(c.tag, {
      x: x + 0.3, y: cy + 0.2, w: cw - 0.6, h: 0.5,
      fontFace: FONT_H, fontSize: 30, color: c.c, bold: true, margin: 0,
    });
    s.addText(c.head, {
      x: x + 0.3, y: cy + 0.78, w: cw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 11, color: C.text, bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(c.sub, {
      x: x + 0.3, y: cy + 1.08, w: cw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 12, color: C.gold, italic: true, margin: 0,
    });
    s.addText(
      c.body.map((it, idx) => ({
        text: it,
        options: { bullet: { code: "25A0" }, color: C.textMid,
                   breakLine: idx < c.body.length - 1 },
      })),
      { x: x + 0.35, y: cy + 1.5, w: cw - 0.7, h: ch - 1.65,
        fontFace: FONT_B, fontSize: 11.5, margin: 0, paraSpaceAfter: 6 }
    );
  });

  s.addText("Sources: ESMA MiCA · Sumsub 2026 · Hagnere Patrimoine 2026 · impots.gouv.fr · Neural Arb MiCA 2026", {
    x: 0.9, y: 6.1, w: 11.5, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted, italic: true, margin: 0,
  });
}

// =============================================================================
// SLIDE 11 — STRATEGIC OPTIONS (Do / Don't)
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "10  ·  STRATEGIC OPTIONS", "Where to spend the next 90 days");
  addFooter(s, 11, TOTAL);

  // Two columns: DO / DON'T
  const lx = 0.9, rx = 7.05, cy2 = 1.7, cw = 5.4, ch = 5.4;

  addCard(s, lx, cy2, cw, ch, C.green);
  s.addText("DO  ·  PRIORITIZE", {
    x: lx + 0.3, y: cy2 + 0.2, w: cw - 0.6, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: C.green, bold: true, charSpacing: 5, margin: 0,
  });
  const doItems = [
    { t: "Push funding capture to live paper", b: "Delta-neutral on Hyperliquid. Net APR 3–12% BTC/ETH, 20–60% mid-caps. Doesn’t consume the same risk budget as ICC." },
    { t: "Re-run walk-forward OOS with friction", b: "Add fees + slippage to the ICC pipeline. Validate that V1 holds out-of-sample before any move toward broker demo." },
    { t: "Portfolio sizing + cross-asset risk", b: "Volatility-targeted sizing, correlation matrix (ETH/SOL/AVAX cluster), drawdown circuit-breaker." },
    { t: "Live monitoring + Telegram alerts", b: "Already wired in config — connect it. Stop-everything switch on DD > X%." },
  ];
  doItems.forEach((it, i) => {
    const y = cy2 + 0.7 + i * 1.13;
    s.addShape(pres.shapes.RECTANGLE, {
      x: lx + 0.3, y: y + 0.1, w: 0.15, h: 0.15,
      fill: { color: C.green }, line: { color: C.green, width: 0 },
    });
    s.addText(it.t, {
      x: lx + 0.55, y, w: cw - 0.8, h: 0.4,
      fontFace: FONT_H, fontSize: 14, color: C.text, bold: true, margin: 0,
    });
    s.addText(it.b, {
      x: lx + 0.55, y: y + 0.4, w: cw - 0.8, h: 0.7,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });

  addCard(s, rx, cy2, cw, ch, C.red);
  s.addText("DON'T  ·  POSTPONE", {
    x: rx + 0.3, y: cy2 + 0.2, w: cw - 0.6, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: C.red, bold: true, charSpacing: 5, margin: 0,
  });
  const dontItems = [
    { t: "Implement INTRADAY / SCALPING modes", b: "Stubs in enum, no code, no M15/M5/M1 data. ~3–6 sessions to build for unclear edge — sub-15-min is the densest SMC battleground." },
    { t: "Download M15/M5/M1 history", b: "Kraken depth is shallow on those TFs. ROI on time would be ahead of model risk. Park until 2027+." },
    { t: "Phase 2 (broker) before OOS validation", b: "Hyperliquid LIVE without robust OOS = textbook overfit-to-live failure mode. 95% of retail bots die here." },
    { t: "Sell signals / copy-trade without CASP", b: "MiCA in force 1 July 2026. Auto-execution for third parties = licence mandatory in the EU." },
  ];
  dontItems.forEach((it, i) => {
    const y = cy2 + 0.7 + i * 1.13;
    s.addShape(pres.shapes.RECTANGLE, {
      x: rx + 0.3, y: y + 0.1, w: 0.15, h: 0.15,
      fill: { color: C.red }, line: { color: C.red, width: 0 },
    });
    s.addText(it.t, {
      x: rx + 0.55, y, w: cw - 0.8, h: 0.4,
      fontFace: FONT_H, fontSize: 14, color: C.text, bold: true, margin: 0,
    });
    s.addText(it.b, {
      x: rx + 0.55, y: y + 0.4, w: cw - 0.8, h: 0.7,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 12 — FINANCIAL PROJECTIONS (3 scenarios)
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "11  ·  FINANCIAL PROJECTIONS", "Three scenarios, low / median / high");
  addFooter(s, 12, TOTAL);

  // Scenario chips
  const chips = [
    { t: "A · NOW",          sub: "ICC V1, 8 assets, no funding yet",          c: C.gold },
    { t: "B · END OF BUILD", sub: "+ funding capture live + realistic friction", c: C.cyan },
    { t: "C · OPTIMIZED",    sub: "Multi-strategy + community / SaaS",            c: C.purple },
  ];
  const cw2 = 4.05, ch2 = 0.95, cgap = 0.2, cyy = 1.7;
  const totW = chips.length * cw2 + (chips.length - 1) * cgap;
  const sx2 = (W - totW) / 2;
  chips.forEach((c, i) => {
    const x = sx2 + i * (cw2 + cgap);
    addCard(s, x, cyy, cw2, ch2, c.c);
    s.addText(c.t, {
      x: x + 0.25, y: cyy + 0.13, w: cw2 - 0.5, h: 0.35,
      fontFace: FONT_B, fontSize: 12, color: c.c, bold: true, charSpacing: 4, margin: 0,
    });
    s.addText(c.sub, {
      x: x + 0.25, y: cyy + 0.48, w: cw2 - 0.5, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });

  // Projection table
  const head = [
    { text: "CAPITAL",     options: { bold: true, color: C.text } },
    { text: "A · LOW",     options: { bold: true, color: C.gold } },
    { text: "A · MEDIAN",  options: { bold: true, color: C.gold } },
    { text: "A · HIGH",    options: { bold: true, color: C.gold } },
    { text: "B · LOW",     options: { bold: true, color: C.cyan } },
    { text: "B · MEDIAN",  options: { bold: true, color: C.cyan } },
    { text: "B · HIGH",    options: { bold: true, color: C.cyan } },
    { text: "C · MEDIAN",  options: { bold: true, color: C.purple } },
  ];
  const proj = [
    ["$10k",  "+$1.2k", "+$2.2k", "+$3.2k",  "+$1.8k", "+$3.0k", "+$4.5k", "n/a*"],
    ["$50k",  "+$6k",   "+$11k",  "+$16k",   "+$9k",   "+$15k",  "+$22.5k","+$70k"],
    ["$100k", "+$12k",  "+$22k",  "+$32k",   "+$18k",  "+$30k",  "+$45k",  "+$70–320k"],
  ];
  s.addTable([head, ...proj], {
    x: 0.9, y: 2.95, w: W - 1.8,
    colW: [1.3, 1.35, 1.35, 1.35, 1.35, 1.35, 1.35, 1.93],
    fontFace: FONT_B, fontSize: 13,
    border: { type: "solid", pt: 0.5, color: C.border },
    fill: { color: C.card },
    color: C.text,
    rowH: 0.55,
    valign: "middle",
    align: "center",
  });

  // Assumptions footer card
  const yA = 5.2;
  addCard(s, 0.9, yA, W - 1.8, 1.55, C.gold, { fill: C.cardAlt });
  s.addText("KEY ASSUMPTIONS", {
    x: 1.1, y: yA + 0.15, w: 11, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.gold, bold: true, charSpacing: 5, margin: 0,
  });
  s.addText([
    { text: "Net Sharpe ", options: { color: C.textMuted } },
    { text: "0.8–1.3 ", options: { color: C.text, bold: true } },
    { text: "live (haircut 30–40% vs backtest)  ·  ", options: { color: C.textMuted } },
    { text: "DD ", options: { color: C.textMuted } },
    { text: "15–25% ", options: { color: C.text, bold: true } },
    { text: "expected live (vs ~7% backtest)  ·  ", options: { color: C.textMuted } },
    { text: "Sizing ", options: { color: C.textMuted } },
    { text: "12.5%/asset ", options: { color: C.text, bold: true } },
    { text: "(equal-weighted)  ·  ", options: { color: C.textMuted } },
    { text: "Friction drag ", options: { color: C.textMuted } },
    { text: "−3 to −5 pp/yr ", options: { color: C.text, bold: true } },
    { text: "before tax  ·  ", options: { color: C.textMuted } },
    { text: "Net of Flat Tax (PFU) 31.4% ", options: { color: C.textMuted } },
    { text: "where applicable.", options: { color: C.textMuted } },
  ], {
    x: 1.1, y: yA + 0.5, w: W - 2.4, h: 0.6,
    fontFace: FONT_B, fontSize: 11, margin: 0,
  });
  s.addText("*Scenario C revenues at $10k capital are dominated by community / signals fees (100–500 subscribers × $20–50/mo).", {
    x: 1.1, y: yA + 1.15, w: W - 2.4, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.textDim, italic: true, margin: 0,
  });
}

// =============================================================================
// SLIDE 13 — RISKS
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "12  ·  RISKS", "What can break this thesis");
  addFooter(s, 13, TOTAL);

  const risks = [
    { t: "EXCHANGE RISK",          c: C.red,
      b: "Hyperliquid: young L1, scaling rapidly. Past incidents on the HLP. Mitigation: split capital across Kraken + Hyperliquid, conservative sizing on the DEX leg." },
    { t: "SMART CONTRACT RISK",    c: C.red,
      b: "Any DEX trade is exposed to chain bugs / oracle manipulation / cross-chain bridge failure. Run only audited contracts; avoid bridged stablecoins of unclear provenance." },
    { t: "REGULATORY RISK · MiCA", c: C.gold,
      b: "Bot for own capital: clear. Bot serving third parties / copy execution: licence required from 1 July 2026. Building monetization paths around this constraint is non-negotiable." },
    { t: "VOLATILITY TAIL RISK",   c: C.purple,
      b: "Crypto VaR(1%) is 10–20× a TradFi book. Flash crashes, stablecoin breaks, liquidation cascades. Mandatory: hard drawdown circuit-breaker, no leverage above 5x even on funding arb." },
    { t: "MODEL / REGIME RISK",    c: C.cyan,
      b: "Backtest sits in a 2024–2025 bull tape. A 2026–2027 bear or rangy regime would compress edge. Walk-forward OOS Session 5 must be re-run with friction before any live capital." },
    { t: "OPERATIONAL RISK",       c: C.green,
      b: "Solo dev, single machine. No CI/CD, no failover, no monitoring yet. Wire Telegram alerts, daily P&L digest, and a stop-everything kill-switch before live." },
  ];
  const gx = 0.9, gy = 1.7;
  const cw = 5.85, ch = 1.6, hg = 0.3, vg = 0.2;
  risks.forEach((r, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = gx + col * (cw + hg), y = gy + row * (ch + vg);
    addCard(s, x, y, cw, ch, r.c);
    // Small square icon
    s.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5,
      fill: { color: r.c, transparency: 75 }, line: { color: r.c, width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.42, y: y + 0.42, w: 0.26, h: 0.26,
      fill: { color: r.c }, line: { color: r.c, width: 0 },
    });
    s.addText(r.t, {
      x: x + 0.95, y: y + 0.25, w: cw - 1.15, h: 0.35,
      fontFace: FONT_H, fontSize: 14, color: r.c, bold: true, charSpacing: 3, margin: 0,
    });
    s.addText(r.b, {
      x: x + 0.95, y: y + 0.6, w: cw - 1.15, h: ch - 0.7,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 14 — MONETIZATION PATHS
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "13  ·  MONETIZATION PATHS", "From own capital to community to SaaS");
  addFooter(s, 14, TOTAL);

  // Funnel-like cascade: 5 horizontal rows
  const paths = [
    { tag: "A", title: "OWN CAPITAL",          eff: "Highest edge capture", risk: "None",                wtp: "100% returns", c: C.gold,    cv: "$20–100k self-funded" },
    { tag: "B", title: "OPEN-SOURCE + PATREON", eff: "Brand, audience, hiring funnel", risk: "Disclosure of edge", wtp: "$5–20 / mo", c: C.cyan, cv: "SMC community ≈ 15–50k active" },
    { tag: "C", title: "SIGNALS DISCORD/TELEGRAM", eff: "Direct monetization", risk: "MiCA if auto-exec", wtp: "$20–100 / mo", c: C.purple, cv: "Subscribers × ticket" },
    { tag: "D", title: "SAAS BOT TURNKEY",     eff: "Scalable",       risk: "Infra + CASP licence", wtp: "$30–100 / mo",     c: C.green,   cv: "Cryptohopper/3Commas benchmarks" },
    { tag: "E", title: "COPY-TRADING POOL",    eff: "Aligned incentives", risk: "Perf-fee structure",   wtp: "0 + 10–30% perf",  c: C.red,     cv: "Finestel / Stoic.ai partnership" },
  ];
  const y0 = 1.7, rh = 0.93, gap = 0.12;
  paths.forEach((p, i) => {
    const y = y0 + i * (rh + gap);
    addCard(s, 0.9, y, W - 1.8, rh, p.c);
    // Big letter
    s.addShape(pres.shapes.RECTANGLE, {
      x: 1.0, y: y + 0.13, w: 0.7, h: 0.67,
      fill: { color: p.c, transparency: 80 }, line: { color: p.c, width: 1 },
    });
    s.addText(p.tag, {
      x: 1.0, y: y + 0.16, w: 0.7, h: 0.65,
      fontFace: FONT_H, fontSize: 26, color: p.c, bold: true,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.title, {
      x: 1.85, y: y + 0.18, w: 4.5, h: 0.6,
      fontFace: FONT_H, fontSize: 15, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.cv, {
      x: 1.85, y: y + 0.5, w: 4.5, h: 0.4,
      fontFace: FONT_B, fontSize: 10, color: C.textMuted, italic: true, margin: 0,
    });
    // 3 mini stats
    const miniCols = [
      { lab: "FIT",  val: p.eff,  col: C.cyan },
      { lab: "RISK", val: p.risk, col: C.red  },
      { lab: "WTP",  val: p.wtp,  col: C.gold },
    ];
    const mx0 = 6.5, mw = 1.85;
    miniCols.forEach((m, k) => {
      const mx = mx0 + k * mw;
      s.addText(m.lab, {
        x: mx, y: y + 0.13, w: mw, h: 0.22,
        fontFace: FONT_B, fontSize: 9, color: m.col, charSpacing: 3, margin: 0,
      });
      s.addText(m.val, {
        x: mx, y: y + 0.36, w: mw, h: 0.5,
        fontFace: FONT_B, fontSize: 11, color: C.text, margin: 0,
      });
    });
  });
}

// =============================================================================
// SLIDE 15 — ROADMAP & NEXT STEPS
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);
  addLeftAccent(s);
  addSlideTitle(s, "14  ·  ROADMAP", "Three phases, gated by validation");
  addFooter(s, 15, TOTAL);

  // 3 horizontal phase blocks
  const phases = [
    { tag: "PHASE 1",  title: "VALIDATE",  win: "Now → +3 mo",     c: C.gold,
      items: [
        "Re-run walk-forward OOS with friction",
        "Add portfolio-level sizing + correlation matrix",
        "Wire Telegram alerts + drawdown circuit-breaker",
        "Push funding_capture branch to live paper on Hyperliquid",
      ] },
    { tag: "PHASE 2",  title: "DEMO + LIVE",       win: "+3 → +9 mo",     c: C.cyan,
      items: [
        "Broker demo (Kraken API, key-restricted)",
        "Real-money $5–10k bootstrap on ICC swing",
        "Funding arb in parallel on Hyperliquid (delta-neutral)",
        "Daily P&L journal + monthly review cadence",
      ] },
    { tag: "PHASE 3",  title: "SCALE / SHARE",   win: "+9 → +18 mo",    c: C.purple,
      items: [
        "Community brick: GitHub partial OSS + Discord",
        "Signals tier (manual-exec only — no MiCA trip)",
        "Evaluate Finestel/Stoic partnership for copy",
        "Decision gate on CASP structure",
      ] },
  ];
  const px = 0.9, py = 1.7;
  const pw = (W - 1.8 - 0.4) / 3, ph = 5.1, pgap = 0.2;
  phases.forEach((p, i) => {
    const x = px + i * (pw + pgap);
    addCard(s, x, py, pw, ph, p.c);
    s.addText(p.tag, {
      x: x + 0.3, y: py + 0.18, w: pw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 11, color: p.c, bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.3, y: py + 0.5, w: pw - 0.6, h: 0.55,
      fontFace: FONT_H, fontSize: 24, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.win, {
      x: x + 0.3, y: py + 1.05, w: pw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 12, color: C.gold, italic: true, margin: 0,
    });
    s.addShape(pres.shapes.LINE, {
      x: x + 0.3, y: py + 1.4, w: pw - 0.6, h: 0,
      line: { color: C.border, width: 0.75 },
    });
    s.addText(
      p.items.map((it, idx) => ({
        text: it,
        options: { bullet: { code: "25A0" }, color: C.textMid,
                   breakLine: idx < p.items.length - 1 },
      })),
      { x: x + 0.35, y: py + 1.55, w: pw - 0.7, h: ph - 1.7,
        fontFace: FONT_B, fontSize: 12.5, margin: 0, paraSpaceAfter: 8 }
    );
  });

  // Bottom progress strip
  const yP = 6.95;
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: yP, w: W - 1.8, h: 0.08,
    fill: { color: C.border }, line: { color: C.border, width: 0 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: yP, w: (W - 1.8) * 0.20, h: 0.08,
    fill: { color: C.gold }, line: { color: C.gold, width: 0 },
  });
}

// =============================================================================
// SLIDE 16 — CLOSING
// =============================================================================
{
  const s = pres.addSlide();
  addBg(s, C.bg);

  // Two side rules — full content height so they don't look truncated
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 0.04, h: H - 1.6,
    fill: { color: C.gold }, line: { color: C.gold, width: 0 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: W - 0.7, y: 1.0, w: 0.02, h: H - 1.6,
    fill: { color: C.cyan, transparency: 60 }, line: { color: C.cyan, width: 0 },
  });

  s.addText("NEXT 90 DAYS", {
    x: 0.9, y: 1.4, w: 11.5, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 8, margin: 0,
  });

  s.addText("Validate. Capture. Scale.", {
    x: 0.85, y: 1.9, w: 11.5, h: 1.0,
    fontFace: FONT_H, fontSize: 52, color: C.text, bold: true, margin: 0,
  });

  s.addText("Hold V1 as default. Re-run walk-forward with realistic friction. " +
            "Push funding capture to live paper in parallel. " +
            "Re-decide at the next gate.", {
    x: 0.85, y: 3.0, w: 11.5, h: 1.0,
    fontFace: FONT_B, fontSize: 18, color: C.textMid, margin: 0,
  });

  // Three action chips
  const acts = [
    { n: "01", t: "OOS WALK-FORWARD", b: "With fees + slippage, 8 assets, 2024–2025." },
    { n: "02", t: "FUNDING CAPTURE LIVE PAPER", b: "Hyperliquid, BTC/ETH/SOL, delta-neutral, ≤ 5x." },
    { n: "03", t: "COMMUNITY BRICK", b: "GitHub OSS + Discord. No auto-exec until MiCA decision." },
  ];
  const aw = 4.0, ah = 1.7, agap = 0.2, ay = 4.7;
  const tw = acts.length * aw + (acts.length - 1) * agap;
  const asx = (W - tw) / 2;
  acts.forEach((a, i) => {
    const x = asx + i * (aw + agap);
    addCard(s, x, ay, aw, ah, C.gold);
    s.addText(a.n, {
      x: x + 0.3, y: ay + 0.15, w: aw - 0.6, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.gold, bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(a.t, {
      x: x + 0.3, y: ay + 0.5, w: aw - 0.6, h: 0.55,
      fontFace: FONT_H, fontSize: 15, color: C.text, bold: true, margin: 0,
    });
    s.addText(a.b, {
      x: x + 0.3, y: ay + 1.05, w: aw - 0.6, h: 0.55,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });

  s.addText("Trading Bot V2  ·  Strategic Deck  ·  May 2026  ·  Confidential", {
    x: 0.9, y: H - 0.45, w: 11.5, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.textMuted,
    charSpacing: 6, margin: 0,
  });
}

// ----- Write ------------------------------------------------------------------
pres.writeFile({ fileName: "/sessions/wizardly-gifted-hypatia/mnt/trading-bot-v2/Trading_Bot_V2_Strategic_Deck_EN.pptx" })
  .then(p => console.log("Wrote:", p))
  .catch(e => { console.error(e); process.exit(1); });
