// Trading Bot V2 — Pitch & Philosophy Deck
// Style: Deep-night cinematic crypto-quant. Pure black + gold + cyan signal + green/red P&L.
// Visual motif: candlestick patterns + signal lines + neural-net brain on data flow slide.
// Output: PPTX → PDF for Badoun's reading on the plane.
//
// Run: NODE_PATH=~/.npm-global/lib/node_modules node scripts/build_pitch_deck.js

const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333" x 7.5"
pres.author = "Trading Bot V2";
pres.title = "Trading Bot V2 — Pitch & Philosophy";

const W = 13.333, H = 7.5;

// --------------------------------------------------------------------- Palette
const C = {
  bg:        "050810",   // near-pure-black with a hint of navy
  bgDeep:    "020308",   // deepest panel
  bgPanel:   "0D131F",   // cards
  bgPanelHi: "131B2A",   // hover/active
  border:    "1F2A3C",
  borderHi:  "364660",

  gold:      "E5B53E",   // institutional gold
  goldDim:   "9C7B25",
  goldFade:  "5C4815",

  cyan:      "22D3EE",   // data / signal
  cyanDim:   "0E7490",
  cyanGlow:  "67E8F9",

  green:     "10D783",   // P&L positive
  greenDim:  "047857",

  red:       "F23A4E",   // P&L negative
  redDim:    "7F1822",

  purple:    "B388FF",   // crypto accent
  purpleDim: "5E35B1",

  text:      "F5F7FA",
  textMid:   "C4CCD8",
  textMuted: "8693A6",
  textDim:   "586475",
};

const FONT_H = "Helvetica Neue";
const FONT_B = "Helvetica";

// -------------------------------------------------------------------- Helpers
function bg(slide, color = C.bg) {
  slide.background = { color };
}

// Stylised candlestick chart background — purely decorative
function drawCandlestickMotif(slide, x0, y0, w, h, opts = {}) {
  const cols = opts.cols || 24;
  const colW = w / cols;
  const baseY = y0 + h * 0.55;
  // Use deterministic pseudo-random based on column index for reproducibility
  for (let i = 0; i < cols; i++) {
    const cx = x0 + i * colW + colW * 0.15;
    const cw = colW * 0.55;
    // Pseudo-random heights
    const ph = ((Math.sin(i * 0.7) + 1) * 0.5 + 0.1) * h * 0.4;
    const dir = (Math.cos(i * 0.5) > 0) ? 1 : -1;
    const cy = baseY - (dir > 0 ? ph : 0);
    const color = dir > 0 ? C.green : C.red;
    // Body
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ph,
      fill: { color, transparency: opts.transparency || 78 },
      line: { color, width: 0 },
    });
    // Wick
    slide.addShape(pres.shapes.LINE, {
      x: cx + cw / 2, y: cy - ph * 0.3, w: 0, h: ph * 1.6,
      line: { color, width: 0.5, transparency: opts.transparency || 78 },
    });
  }
}

// Sine-wave style "signal" line
function drawSignalLine(slide, x0, y0, w, h, color = C.cyan, opts = {}) {
  const segments = opts.segments || 80;
  const segW = w / segments;
  const amplitude = h * 0.35;
  const cy = y0 + h / 2;
  const trans = opts.transparency || 50;
  // Build piecewise line approximations
  for (let i = 0; i < segments; i++) {
    const x1 = x0 + i * segW;
    const x2 = x0 + (i + 1) * segW;
    const y1 = cy + Math.sin(i * 0.25) * amplitude * (1 - i / segments * 0.3);
    const y2 = cy + Math.sin((i + 1) * 0.25) * amplitude * (1 - (i + 1) / segments * 0.3);
    slide.addShape(pres.shapes.LINE, {
      x: x1, y: y1, w: x2 - x1, h: y2 - y1,
      line: { color, width: opts.width || 1.5, transparency: trans },
    });
  }
}

// Vertical golden rule motif
function goldRule(slide, x, yStart, yEnd, opts = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y: yStart, w: opts.width || 0.04, h: yEnd - yStart,
    fill: { color: opts.color || C.gold, transparency: opts.transparency || 0 },
    line: { color: opts.color || C.gold, width: 0 },
  });
}

function dot(slide, x, y, size, color) {
  slide.addShape(pres.shapes.OVAL, {
    x: x - size / 2, y: y - size / 2, w: size, h: size,
    fill: { color }, line: { color, width: 0 },
  });
}

function addSlideTitle(slide, eyebrow, title, opts = {}) {
  slide.addText(eyebrow, {
    x: 0.7, y: 0.55, w: 11.5, h: 0.35,
    fontFace: FONT_B, fontSize: 11, color: C.gold,
    bold: true, charSpacing: 8, margin: 0,
  });
  slide.addText(title, {
    x: 0.7, y: 0.9, w: 12, h: 0.9,
    fontFace: FONT_H, fontSize: opts.size || 32, color: C.text,
    bold: true, margin: 0,
  });
}

function addFooter(slide, num, total) {
  slide.addShape(pres.shapes.LINE, {
    x: 0.7, y: H - 0.45, w: W - 1.4, h: 0,
    line: { color: C.border, width: 0.5 },
  });
  slide.addText("TRADING BOT V2  ·  PITCH & PHILOSOPHY", {
    x: 0.7, y: H - 0.38, w: 7, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.textDim,
    charSpacing: 4, margin: 0,
  });
  slide.addText(`${num} / ${total}`, {
    x: W - 1.7, y: H - 0.38, w: 1, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.textDim,
    align: "right", margin: 0,
  });
}

const TOTAL = 14;

// =============================================================================
// SLIDE 1 — HERO TITLE
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);

  // Bottom candlestick motif very faded
  drawCandlestickMotif(s, 0, H - 2.2, W, 2, { transparency: 88 });

  // Top signal lines
  drawSignalLine(s, 0, 1.5, W, 2.5, C.cyan, { transparency: 72, segments: 100, width: 0.7 });
  drawSignalLine(s, 0, 1.7, W, 2.2, C.gold, { transparency: 80, segments: 80, width: 0.5 });

  // Gold accents
  goldRule(s, 0.8, 0.5, H - 1, { width: 0.03 });
  goldRule(s, W - 0.85, 0.5, H - 1, { width: 0.02, color: C.cyan, transparency: 40 });

  // Top eyebrow
  s.addText("A CRYPTO QUANT SYSTEM  ·  HYPERLIQUID + KRAKEN  ·  MAY 2026", {
    x: 1.0, y: 1.1, w: 11.5, h: 0.4,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 10, margin: 0,
  });

  // Massive title
  s.addText("Trading Bot V2", {
    x: 1.0, y: 1.8, w: 11.5, h: 1.5,
    fontFace: FONT_H, fontSize: 88, color: C.text,
    bold: true, margin: 0,
  });

  // Tagline — italicized cyan
  s.addText("Built on rigor.  Powered by structural edges.  Operated by transparency.", {
    x: 1.0, y: 3.5, w: 11.5, h: 0.6,
    fontFace: FONT_H, fontSize: 22, color: C.cyan,
    italic: true, margin: 0,
  });

  // Three pillars at the bottom
  const pillars = [
    { tag: "01", title: "RIGOR",         body: "94/94 unit tests · OOS validation · No-lookahead audited" },
    { tag: "02", title: "STRUCTURE",     body: "Funding capture carry + ICC pattern = barbell strategy" },
    { tag: "03", title: "TRANSPARENCY",  body: "Belief-stage tracking · Honest haircuts · No false claims" },
  ];
  const pw = 4.0, ph_card = 1.5, pgap = 0.25;
  const ptw = pillars.length * pw + (pillars.length - 1) * pgap;
  const psx = (W - ptw) / 2;
  pillars.forEach((p, i) => {
    const x = psx + i * (pw + pgap);
    const y = 5.0;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: pw, h: ph_card,
      fill: { color: C.bgPanel, transparency: 20 },
      line: { color: C.border, width: 0.5 },
    });
    // Tag in gold
    s.addText(p.tag, {
      x: x + 0.3, y: y + 0.15, w: pw - 0.6, h: 0.3,
      fontFace: FONT_B, fontSize: 11, color: C.gold,
      bold: true, charSpacing: 5, margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.3, y: y + 0.45, w: pw - 0.6, h: 0.45,
      fontFace: FONT_H, fontSize: 22, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.body, {
      x: x + 0.3, y: y + 0.95, w: pw - 0.6, h: 0.45,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });

  s.addText("Prepared for Badoun  ·  May 2026  ·  Confidential", {
    x: 1.0, y: H - 0.45, w: 11.5, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textDim,
    charSpacing: 6, margin: 0,
  });
}

// =============================================================================
// SLIDE 2 — THE PROBLEM
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "01  ·  THE PROBLEM", "Why most crypto trading bots fail");
  addFooter(s, 2, TOTAL);

  // Big stat
  s.addText("95%", {
    x: 0.9, y: 2.0, w: 4.5, h: 2.0,
    fontFace: FONT_H, fontSize: 140, color: C.red,
    bold: true, margin: 0,
  });
  s.addText("of retail AI trading bots lose money within 90 days.", {
    x: 0.9, y: 4.0, w: 5.5, h: 0.9,
    fontFace: FONT_H, fontSize: 16, color: C.text, margin: 0,
  });
  s.addText("Source: GoatFundedTrader, multi-year retail bot tracking 2024-26.", {
    x: 0.9, y: 4.9, w: 5.5, h: 0.4,
    fontFace: FONT_B, fontSize: 9, color: C.textDim, italic: true, margin: 0,
  });

  // Right column: 3 causes
  const causes = [
    { n: "1", title: "OVERFITTING", body: "Strategies tuned to past data don't generalize. Beautiful backtests, ugly live runs." },
    { n: "2", title: "FRICTION IGNORED", body: "Backtests skip real fees, slippage, funding. Live P&L often 30-50% below the brochure." },
    { n: "3", title: "NO RISK DISCIPLINE", body: "No sizing rules, no kill switch, no drawdown control. Capital lasts until the first big move." },
  ];
  const cx = 7.0, cy0 = 1.8, cw = 5.6, ch = 1.55, cgap = 0.15;
  causes.forEach((c, i) => {
    const y = cy0 + i * (ch + cgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y, w: cw, h: ch,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y, w: 0.05, h: ch,
      fill: { color: C.red }, line: { color: C.red, width: 0 },
    });
    // Big number
    s.addText(c.n, {
      x: cx + 0.2, y: y + 0.2, w: 0.7, h: 1.1,
      fontFace: FONT_H, fontSize: 50, color: C.red,
      bold: true, margin: 0,
    });
    s.addText(c.title, {
      x: cx + 1.0, y: y + 0.2, w: cw - 1.1, h: 0.4,
      fontFace: FONT_H, fontSize: 16, color: C.text, bold: true, margin: 0,
    });
    s.addText(c.body, {
      x: cx + 1.0, y: y + 0.65, w: cw - 1.1, h: 0.85,
      fontFace: FONT_B, fontSize: 12, color: C.textMid, margin: 0,
    });
  });

  // Tagline at bottom
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 6.0, w: W - 1.8, h: 0.7,
    fill: { color: C.bgPanelHi }, line: { color: C.gold, width: 0.5 },
  });
  s.addText([
    { text: "V2'S ANSWER  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "We measure honestly, validate out-of-sample, model real friction, and size with discipline.", options: { color: C.text } },
  ], {
    x: 1.1, y: 6.15, w: W - 2.2, h: 0.45,
    fontFace: FONT_B, fontSize: 14, margin: 0,
  });
}

// =============================================================================
// SLIDE 3 — WHAT V2 IS
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "02  ·  WHAT V2 IS", "An honest, transparent crypto quant system");
  addFooter(s, 3, TOTAL);

  // Faded candle motif at bottom
  drawCandlestickMotif(s, 0, H - 2, W, 1.5, { transparency: 90 });

  // The one-liner
  s.addText([
    { text: "Trading Bot V2 is a ", options: { color: C.textMid } },
    { text: "Python ", options: { color: C.purple, bold: true } },
    { text: "trading system that ", options: { color: C.textMid } },
    { text: "captures funding-rate carry ", options: { color: C.cyan, bold: true } },
    { text: "on Hyperliquid and ", options: { color: C.textMid } },
    { text: "trades ICC swing patterns ", options: { color: C.gold, bold: true } },
    { text: "on a filtered universe of major altcoins — with backtests, walk-forward, friction, and risk all measured before any capital is deployed.", options: { color: C.textMid } },
  ], {
    x: 0.9, y: 2.0, w: W - 1.8, h: 1.5,
    fontFace: FONT_H, fontSize: 18, margin: 0,
  });

  // 4 building blocks
  const blocks = [
    { tag: "DATA",       sub: "Kraken 12y + HL public", c: C.cyan },
    { tag: "STRATEGY",   sub: "Funding + ICC + future strats",     c: C.gold },
    { tag: "RISK",       sub: "Kelly fractional + caps", c: C.purple },
    { tag: "EXECUTION",  sub: "Paper now · Live Phase 2",      c: C.green },
  ];
  const bw = 2.85, bh = 1.5, bgap = 0.25, by = 4.0;
  const btw = blocks.length * bw + (blocks.length - 1) * bgap;
  const bsx = (W - btw) / 2;
  blocks.forEach((b, i) => {
    const x = bsx + i * (bw + bgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: by, w: bw, h: bh,
      fill: { color: C.bgPanel }, line: { color: b.c, width: 1 },
    });
    s.addText(b.tag, {
      x, y: by + 0.3, w: bw, h: 0.7,
      fontFace: FONT_H, fontSize: 24, color: b.c, bold: true,
      align: "center", margin: 0,
    });
    s.addText(b.sub, {
      x: x + 0.2, y: by + 0.9, w: bw - 0.4, h: 0.5,
      fontFace: FONT_B, fontSize: 11, color: C.textMid,
      align: "center", margin: 0,
    });
    if (i < blocks.length - 1) {
      s.addText("→", {
        x: x + bw - 0.05, y: by + bh / 2 - 0.25, w: bgap + 0.1, h: 0.5,
        fontFace: FONT_H, fontSize: 20, color: C.gold,
        align: "center", margin: 0,
      });
    }
  });

  // Single pull-quote at bottom
  s.addText("Not a bot. A discipline.", {
    x: 0.9, y: 5.85, w: W - 1.8, h: 0.7,
    fontFace: FONT_H, fontSize: 28, color: C.cyan,
    italic: true, align: "center", margin: 0,
  });
}

// =============================================================================
// SLIDE 4 — MISSION
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bgDeep);

  // Decorative left vertical bar + a faint right candle motif
  goldRule(s, 0.8, 1.5, H - 1, { width: 0.05 });
  drawCandlestickMotif(s, W * 0.55, 2.0, W * 0.5, H - 4, { transparency: 92 });

  s.addText("MISSION", {
    x: 1.2, y: 1.6, w: 8, h: 0.5,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 10, margin: 0,
  });

  // The mission statement — large, prominent, multi-line
  s.addText([
    { text: "To build", options: { color: C.textMid, italic: true } },
    { text: " an algorithmic trading system ", options: { color: C.text, bold: true } },
    { text: "that survives the contact with reality —", options: { color: C.textMid, italic: true } },
  ], {
    x: 1.2, y: 2.2, w: W - 2.4, h: 1.2,
    fontFace: FONT_H, fontSize: 30, margin: 0,
  });

  s.addText([
    { text: "by measuring rigorously, ", options: { color: C.cyan } },
    { text: "respecting risk, ", options: { color: C.gold } },
    { text: "and reporting honestly", options: { color: C.green } },
    { text: " — even when it hurts the project.", options: { color: C.textMid, italic: true } },
  ], {
    x: 1.2, y: 3.7, w: W - 2.4, h: 1.5,
    fontFace: FONT_H, fontSize: 30, margin: 0,
  });

  // Bottom signature
  s.addShape(pres.shapes.LINE, {
    x: 1.2, y: 6.3, w: 5.5, h: 0,
    line: { color: C.gold, width: 1 },
  });
  s.addText("— The V2 charter", {
    x: 1.2, y: 6.4, w: 8, h: 0.4,
    fontFace: FONT_B, fontSize: 13, color: C.gold,
    italic: true, charSpacing: 3, margin: 0,
  });

  addFooter(s, 4, TOTAL);
}

// =============================================================================
// SLIDE 5 — PHILOSOPHY
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "03  ·  PHILOSOPHY", "Five principles that shape every decision");
  addFooter(s, 5, TOTAL);

  const principles = [
    { n: "I",   title: "RADICAL TRANSPARENCY",
      body: "Every claim qualified. Every backtest tagged with methodology + friction + window + regime. No hidden caveats.",
      c: C.gold },
    { n: "II",  title: "NO OVERFIT",
      body: "Fixed parameters from spec, not data-mined. Walk-forward strict. Filter universe validated on untouched windows.",
      c: C.cyan },
    { n: "III", title: "STRUCTURAL EDGE > PATTERN",
      body: "Funding capture (structural carry) is the spine. Pattern strategies (ICC) are decorations, not the load-bearing wall.",
      c: C.green },
    { n: "IV",  title: "BELIEF, NOT FAITH",
      body: "Belief-stage % tracked openly. Drops below 50% → pivot proposal. Construction stage and belief stage clearly separated.",
      c: C.purple },
    { n: "V",   title: "OPTIONALITY PRESERVED",
      body: "V2 must remain a serious option, never a desperate bet. Kill criteria written before drawdowns. Capital exposure capped.",
      c: C.red },
  ];

  // Grid: 5 cards in horizontal row with a wide spacing
  const cw = 2.4, ch = 4.5, cgap = 0.15, cy = 1.85;
  const ctw = principles.length * cw + (principles.length - 1) * cgap;
  const csx = (W - ctw) / 2;
  principles.forEach((p, i) => {
    const x = csx + i * (cw + cgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cy, w: cw, h: ch,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
    });
    // Top accent
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cy, w: cw, h: 0.06,
      fill: { color: p.c }, line: { color: p.c, width: 0 },
    });
    // Roman numeral
    s.addText(p.n, {
      x, y: cy + 0.3, w: cw, h: 0.8,
      fontFace: FONT_H, fontSize: 44, color: p.c,
      bold: true, align: "center", margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.15, y: cy + 1.3, w: cw - 0.3, h: 0.6,
      fontFace: FONT_B, fontSize: 11, color: C.text,
      bold: true, charSpacing: 3, align: "center", margin: 0,
    });
    s.addText(p.body, {
      x: x + 0.2, y: cy + 2.0, w: cw - 0.4, h: ch - 2.1,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 6 — THE EDGE
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "04  ·  THE EDGE", "A barbell strategy — structural carry meets pattern hunting");
  addFooter(s, 6, TOTAL);

  // Two-column comparison
  const lx = 0.9, rx = 7.05, cy = 1.8, cw = 5.4, ch = 4.85;

  // Funding capture (left, dominant)
  s.addShape(pres.shapes.RECTANGLE, {
    x: lx, y: cy, w: cw, h: ch,
    fill: { color: C.bgPanel }, line: { color: C.green, width: 1.5 },
  });
  s.addText("FUNDING CAPTURE", {
    x: lx + 0.3, y: cy + 0.2, w: cw - 0.6, h: 0.5,
    fontFace: FONT_B, fontSize: 12, color: C.green,
    bold: true, charSpacing: 5, margin: 0,
  });
  s.addText("Structural", {
    x: lx + 0.3, y: cy + 0.6, w: cw - 0.6, h: 0.8,
    fontFace: FONT_H, fontSize: 36, color: C.text, bold: true, margin: 0,
  });
  // Mini signal line as decoration
  drawSignalLine(s, lx + 0.3, cy + 1.4, cw - 0.6, 0.5, C.green, { segments: 60, width: 1.5, transparency: 30 });

  const fundingItems = [
    { k: "Edge type",  v: "Risk premium · retail longs pay" },
    { k: "Direction",  v: "Delta-neutral · uncorrelated" },
    { k: "Net APR",    v: "3–12% majors · 20–60% mid-caps" },
    { k: "Erosion risk", v: "Low — needs retail behavior change" },
    { k: "Tail risk",  v: "Liquidation cascade (mitigated)" },
    { k: "Capital eff.", v: "0.5x — needs collateral" },
  ];
  fundingItems.forEach((it, i) => {
    const y = cy + 2.1 + i * 0.42;
    s.addText(it.k.toUpperCase(), {
      x: lx + 0.3, y, w: 2.0, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(it.v, {
      x: lx + 2.2, y, w: cw - 2.4, h: 0.3,
      fontFace: FONT_B, fontSize: 11, color: C.text, margin: 0,
    });
  });

  // ICC swing (right)
  s.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: cy, w: cw, h: ch,
    fill: { color: C.bgPanel }, line: { color: C.gold, width: 1.5 },
  });
  s.addText("ICC SWING", {
    x: rx + 0.3, y: cy + 0.2, w: cw - 0.6, h: 0.5,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 5, margin: 0,
  });
  s.addText("Pattern", {
    x: rx + 0.3, y: cy + 0.6, w: cw - 0.6, h: 0.8,
    fontFace: FONT_H, fontSize: 36, color: C.text, bold: true, margin: 0,
  });
  drawCandlestickMotif(s, rx + 0.3, cy + 1.4, cw - 0.6, 0.5, { transparency: 60, cols: 20 });

  const iccItems = [
    { k: "Edge type",  v: "Behavioral · market structure" },
    { k: "Direction",  v: "Long & short · directional" },
    { k: "Sharpe OOS", v: "0.84–2.22 (with friction)" },
    { k: "Erosion risk", v: "Moderate — SMC mainstream growing" },
    { k: "Tail risk",  v: "Bounded by structural SL" },
    { k: "Capital eff.", v: "1x — full notional" },
  ];
  iccItems.forEach((it, i) => {
    const y = cy + 2.1 + i * 0.42;
    s.addText(it.k.toUpperCase(), {
      x: rx + 0.3, y, w: 2.0, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(it.v, {
      x: rx + 2.2, y, w: cw - 2.4, h: 0.3,
      fontFace: FONT_B, fontSize: 11, color: C.text, margin: 0,
    });
  });

  // Bottom annotation: the barbell
  s.addText([
    { text: "TALEB BARBELL  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "Stable carry on one end, asymmetric pattern hunting on the other. Anti-fragile by construction.", options: { color: C.textMid, italic: true } },
  ], {
    x: 0.9, y: 6.8, w: W - 1.8, h: 0.4,
    fontFace: FONT_B, fontSize: 11, align: "center", margin: 0,
  });
}

// =============================================================================
// SLIDE 7 — HOW IT WORKS (BRAIN / PIPELINE DIAGRAM)
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "05  ·  HOW IT WORKS", "Data flows in, decisions flow out");
  addFooter(s, 7, TOTAL);

  // Layout: 5 nodes from left to right, connected by curved lines
  const nodes = [
    { x: 1.3,  y: 4.0, label: "EXCHANGES",   sub: "HL · Kraken",        c: C.purple },
    { x: 4.0,  y: 2.5, label: "FUNDING",     sub: "1h public feed",     c: C.cyan },
    { x: 4.0,  y: 5.5, label: "OHLC",        sub: "D / H4 / H1",        c: C.cyan },
    { x: 6.7,  y: 4.0, label: "BRAIN",       sub: "Decision engine",    c: C.gold,    big: true },
    { x: 9.4,  y: 2.5, label: "FUNDING CAP", sub: "Δ-neutral trades",   c: C.green },
    { x: 9.4,  y: 5.5, label: "ICC SWING",   sub: "Long/short setups",  c: C.green },
    { x: 12.0, y: 4.0, label: "PAPER → LIVE", sub: "Risk-controlled",   c: C.red },
  ];

  // Draw connections (lines) BEFORE the nodes so they appear behind
  const conns = [
    [0, 1], [0, 2],
    [1, 3], [2, 3],
    [3, 4], [3, 5],
    [4, 6], [5, 6],
  ];
  conns.forEach(([a, b]) => {
    const na = nodes[a], nb = nodes[b];
    // Draw a thin line
    s.addShape(pres.shapes.LINE, {
      x: na.x, y: na.y, w: nb.x - na.x, h: nb.y - na.y,
      line: { color: C.gold, width: 0.8, transparency: 50 },
    });
    // Small data-dot moving along the line (just decorative midpoint)
    dot(s, (na.x + nb.x) / 2, (na.y + nb.y) / 2, 0.07, C.cyan);
  });

  // Draw nodes
  nodes.forEach(n => {
    const size = n.big ? 1.2 : 0.85;
    // Outer glow ring
    s.addShape(pres.shapes.OVAL, {
      x: n.x - size / 2 - 0.1, y: n.y - size / 2 - 0.1, w: size + 0.2, h: size + 0.2,
      fill: { color: n.c, transparency: 80 },
      line: { color: n.c, width: 0.5, transparency: 60 },
    });
    // Inner circle
    s.addShape(pres.shapes.OVAL, {
      x: n.x - size / 2, y: n.y - size / 2, w: size, h: size,
      fill: { color: C.bgPanel },
      line: { color: n.c, width: n.big ? 2 : 1.5 },
    });
    // For the BRAIN node: label INSIDE the circle (it's the centerpiece).
    // For all other nodes: label below the circle.
    if (n.big) {
      s.addText(n.label, {
        x: n.x - 0.7, y: n.y - 0.2, w: 1.4, h: 0.4,
        fontFace: FONT_H, fontSize: 13, color: n.c,
        bold: true, align: "center", margin: 0,
      });
      s.addText(n.sub, {
        x: n.x - 1.2, y: n.y + size / 2 + 0.15, w: 2.4, h: 0.3,
        fontFace: FONT_B, fontSize: 10, color: C.textMuted,
        italic: true, align: "center", margin: 0,
      });
    } else {
      s.addText(n.label, {
        x: n.x - 1.2, y: n.y + size / 2 + 0.08, w: 2.4, h: 0.3,
        fontFace: FONT_B, fontSize: 10, color: n.c,
        bold: true, charSpacing: 3, align: "center", margin: 0,
      });
      s.addText(n.sub, {
        x: n.x - 1.2, y: n.y + size / 2 + 0.4, w: 2.4, h: 0.3,
        fontFace: FONT_B, fontSize: 9, color: C.textMuted,
        align: "center", margin: 0,
      });
    }
  });

  // Bottom annotation
  s.addText([
    { text: "Decision engine consumes funding history + OHLC, applies V1 SL rules + funding signal logic, and emits orders — paper today, live tomorrow.",
      options: { color: C.textMid, italic: true } },
  ], {
    x: 0.9, y: 6.7, w: W - 1.8, h: 0.4,
    fontFace: FONT_B, fontSize: 12, align: "center", margin: 0,
  });
}

// =============================================================================
// SLIDE 8 — CURRENT STATE
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "06  ·  CURRENT STATE", "Where the system stands on 21 May 2026");
  addFooter(s, 8, TOTAL);

  // 4-qualifier line
  s.addText("METHODO walk-forward OOS · FRICTION fees + slippage + funding · WINDOW 2024-25 bull + 2022-23 bear · REGIME both", {
    x: 0.9, y: 1.7, w: W - 1.8, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.cyan, italic: true, charSpacing: 2, margin: 0,
  });

  // Top KPI strip — 4 big numbers
  const kpis = [
    { v: "4 / 8",   l: "FILTERED UNIVERSE", c: C.gold },
    { v: "2.22",    l: "SHARPE · BULL OOS",  c: C.green },
    { v: "1.07",    l: "SHARPE · BEAR OOS",  c: C.green },
    { v: "70%",     l: "BELIEF STAGE",       c: C.cyan },
  ];
  const kw = 3.0, kh = 1.4, kgap = 0.15, ky = 2.15;
  const ktw = kpis.length * kw + (kpis.length - 1) * kgap;
  const ksx = (W - ktw) / 2;
  kpis.forEach((k, i) => {
    const x = ksx + i * (kw + kgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: ky, w: kw, h: kh,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: ky, w: kw, h: 0.05,
      fill: { color: k.c }, line: { color: k.c, width: 0 },
    });
    s.addText(k.v, {
      x: x + 0.2, y: ky + 0.15, w: kw - 0.4, h: 0.7,
      fontFace: FONT_H, fontSize: 36, color: k.c, bold: true, margin: 0,
    });
    s.addText(k.l, {
      x: x + 0.2, y: ky + 0.85, w: kw - 0.4, h: 0.35,
      fontFace: FONT_B, fontSize: 10, color: C.textMuted, charSpacing: 3, margin: 0,
    });
  });

  // 4 assets visualization
  const assets = [
    { sym: "ETH",  pf: "26.6",  pnl: "+59pp",  c: C.green },
    { sym: "LTC",  pf: "7.09",  pnl: "+52pp",  c: C.green },
    { sym: "AVAX", pf: "2.04",  pnl: "+17pp",  c: C.gold },
    { sym: "SOL",  pf: "2.77",  pnl: "+25pp",  c: C.gold },
  ];
  const ay = 4.0, ah = 1.6, aw = 3.0, agap = 0.15;
  const atw = assets.length * aw + (assets.length - 1) * agap;
  const asx = (W - atw) / 2;
  s.addText("FILTERED 4-ASSET UNIVERSE (PF · ΣPnL bull-window OOS)", {
    x: 0.9, y: 3.7, w: W - 1.8, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.textMuted,
    charSpacing: 3, align: "center", margin: 0,
  });
  assets.forEach((a, i) => {
    const x = asx + i * (aw + agap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: ay, w: aw, h: ah,
      fill: { color: C.bgPanel }, line: { color: a.c, width: 1 },
    });
    s.addText(a.sym, {
      x: x + 0.2, y: ay + 0.15, w: aw - 0.4, h: 0.5,
      fontFace: FONT_H, fontSize: 24, color: a.c, bold: true, margin: 0,
    });
    s.addText("PF", {
      x: x + 0.2, y: ay + 0.7, w: 1, h: 0.25,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(a.pf, {
      x: x + 0.2, y: ay + 0.92, w: 1.2, h: 0.4,
      fontFace: FONT_H, fontSize: 18, color: C.text, bold: true, margin: 0,
    });
    s.addText("PNL", {
      x: x + 1.6, y: ay + 0.7, w: 1, h: 0.25,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(a.pnl, {
      x: x + 1.6, y: ay + 0.92, w: 1.2, h: 0.4,
      fontFace: FONT_H, fontSize: 18, color: a.c, bold: true, margin: 0,
    });
  });

  // Status pills at bottom
  const status = [
    { icon: "●", text: "Paper trading running autonomously",   c: C.green },
    { icon: "●", text: "Telegram alerting + watchdog active",  c: C.green },
    { icon: "●", text: "No live capital deployed yet",         c: C.gold },
    { icon: "●", text: "Phase 2 broker demo: post-validation", c: C.cyan },
  ];
  const sy = 6.0;
  status.forEach((st, i) => {
    const y = sy + i * 0.32;
    s.addText(st.icon, {
      x: 0.9, y, w: 0.3, h: 0.3,
      fontFace: FONT_H, fontSize: 16, color: st.c, margin: 0,
    });
    s.addText(st.text, {
      x: 1.2, y, w: 11, h: 0.3,
      fontFace: FONT_B, fontSize: 12, color: C.text, margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 9 — WHY NOW
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "07  ·  WHY NOW", "Three macro tailwinds align in 2026");
  addFooter(s, 9, TOTAL);

  const reasons = [
    {
      tag: "MARKET",
      head: "Hyperliquid captures 44% of perp-DEX volume",
      stat: "+8 pp",
      sub: "share gain since January 2026 — only major perp venue gaining share",
      body: "Best-in-class fees (0.015/0.045 bps), hourly funding, on-chain transparency. The infrastructure curve V2 rides.",
      c: C.cyan,
      source: "yellow.com · DeFiLlama"
    },
    {
      tag: "REGULATION",
      head: "MiCA goes live 1 July 2026",
      stat: "01.07.26",
      sub: "Clarity for proprietary trading. Barrier for unlicensed copy/SaaS — a moat for compliant operators.",
      body: "DAC8 transmission auto since January. Grey-zone era over. Early movers with clean operations have advantage.",
      c: C.gold,
      source: "ESMA · Sumsub 2026"
    },
    {
      tag: "PRODUCT",
      head: "Retail SMC bots dominate visuals, not execution",
      stat: "$0",
      sub: "Almost no end-to-end Python ICC bot exists publicly. The vertical is empty.",
      body: "LuxAlgo, SMRT Algo, ICT — all indicators. Cryptohopper, 3Commas — all SaaS. V2 sits in the white space.",
      c: C.purple,
      source: "TradingView · industry scan"
    },
  ];

  const ry = 1.75, rh = 1.65, rgap = 0.12;
  reasons.forEach((r, i) => {
    const y = ry + i * (rh + rgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.9, y, w: W - 1.8, h: rh,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.9, y, w: 0.05, h: rh,
      fill: { color: r.c }, line: { color: r.c, width: 0 },
    });
    // Tag
    s.addText(r.tag, {
      x: 1.15, y: y + 0.18, w: 2, h: 0.3,
      fontFace: FONT_B, fontSize: 10, color: r.c,
      bold: true, charSpacing: 5, margin: 0,
    });
    // Headline
    s.addText(r.head, {
      x: 1.15, y: y + 0.45, w: 6.5, h: 0.45,
      fontFace: FONT_H, fontSize: 18, color: C.text, bold: true, margin: 0,
    });
    // Sub
    s.addText(r.sub, {
      x: 1.15, y: y + 0.9, w: 6.5, h: 0.4,
      fontFace: FONT_B, fontSize: 11, color: C.textMid, margin: 0,
    });
    // Body
    s.addText(r.body, {
      x: 1.15, y: y + 1.25, w: 6.5, h: 0.35,
      fontFace: FONT_B, fontSize: 10, color: C.textMuted, italic: true, margin: 0,
    });
    // Big stat on the right
    s.addText(r.stat, {
      x: 8.0, y: y + 0.2, w: 3.5, h: 1.1,
      fontFace: FONT_H, fontSize: 50, color: r.c,
      bold: true, align: "right", margin: 0,
    });
    s.addText(r.source, {
      x: 8.0, y: y + 1.3, w: 3.5, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textDim,
      italic: true, align: "right", margin: 0,
    });
  });
}

// =============================================================================
// SLIDE 10 — VISION (24-MONTH TRAJECTORY)
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "08  ·  VISION", "A 24-month trajectory from solo bot to community + scale");
  addFooter(s, 10, TOTAL);

  // Horizontal timeline with 5 phases
  const phases = [
    { tag: "PH 1",  title: "VALIDATE",         when: "Now → +3 mo",   c: C.gold },
    { tag: "PH 2",  title: "DEMO + LIVE",      when: "+3 → +9 mo",    c: C.cyan },
    { tag: "PH 3",  title: "SCALE + COMMUNITY", when: "+9 → +18 mo",   c: C.green },
    { tag: "PH 4",  title: "MULTI-STRAT",      when: "+18 → +24 mo",  c: C.purple },
    { tag: "PH 5",  title: "DPM EVAL",         when: "+24 mo",        c: C.red },
  ];

  const lineY = 4.0;
  const pStart = 1.5, pEnd = W - 1.5;
  // Horizontal connector
  s.addShape(pres.shapes.LINE, {
    x: pStart, y: lineY, w: pEnd - pStart, h: 0,
    line: { color: C.gold, width: 1.5 },
  });
  // Phase markers
  const step = (pEnd - pStart) / (phases.length - 1);
  phases.forEach((p, i) => {
    const cx = pStart + i * step;
    // Outer + inner circle (node)
    s.addShape(pres.shapes.OVAL, {
      x: cx - 0.45, y: lineY - 0.45, w: 0.9, h: 0.9,
      fill: { color: C.bg }, line: { color: p.c, width: 2 },
    });
    s.addText(p.tag, {
      x: cx - 0.45, y: lineY - 0.25, w: 0.9, h: 0.5,
      fontFace: FONT_B, fontSize: 12, color: p.c, bold: true,
      align: "center", margin: 0,
    });
    // Vertical label above/below alternately
    const isUp = i % 2 === 0;
    const labelY = isUp ? lineY - 2.0 : lineY + 0.6;
    s.addText(p.title, {
      x: cx - 1.5, y: labelY, w: 3.0, h: 0.4,
      fontFace: FONT_H, fontSize: 14, color: C.text, bold: true,
      align: "center", margin: 0,
    });
    s.addText(p.when, {
      x: cx - 1.5, y: labelY + 0.4, w: 3.0, h: 0.3,
      fontFace: FONT_B, fontSize: 10, color: p.c, italic: true,
      align: "center", margin: 0,
    });

    // Connector from label to node
    const connY1 = isUp ? labelY + 0.7 : lineY + 0.45;
    const connY2 = isUp ? lineY - 0.45 : labelY;
    s.addShape(pres.shapes.LINE, {
      x: cx, y: connY1, w: 0, h: connY2 - connY1,
      line: { color: p.c, width: 0.75, transparency: 40 },
    });
  });

  // Bottom narrative panel
  const yN = 6.0;
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: yN, w: W - 1.8, h: 0.95,
    fill: { color: C.bgPanelHi }, line: { color: C.gold, width: 0.5 },
  });
  s.addText([
    { text: "TRAJECTORY  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "Each phase gates the next. We don't deploy capital before OOS validates. We don't build SaaS before community validates. We don't seek licence before product validates.",
      options: { color: C.text } },
  ], {
    x: 1.1, y: yN + 0.2, w: W - 2.2, h: 0.6,
    fontFace: FONT_B, fontSize: 12, italic: true, margin: 0,
  });
}

// =============================================================================
// SLIDE 11 — AMBITIONS / MONETIZATION LADDER
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "09  ·  AMBITIONS", "Seven possible levels — each with its tradeoffs");
  addFooter(s, 11, TOTAL);

  const ladder = [
    { lvl: "1", title: "PROPRIETARY",       sub: "Own capital, no third party",      revenue: "100% of edge",         license: "None",  c: C.green },
    { lvl: "2", title: "OPEN-SOURCE + PATREON", sub: "Community + soft monetization", revenue: "$1-5k/mo at 100-500 subs", license: "None",  c: C.cyan },
    { lvl: "3", title: "SIGNAL CHANNEL",    sub: "Discord/Telegram paid",            revenue: "$20-100 / sub / mo",   license: "Border-line",    c: C.cyan },
    { lvl: "4", title: "TURNKEY SaaS",      sub: "Customer connects exchange",       revenue: "$30-100 / customer / mo", license: "CASP",  c: C.purple },
    { lvl: "5", title: "COPY-TRADING POOL", sub: "Via Finestel / Stoic partnership", revenue: "10-30% perf fee",      license: "Partner",         c: C.purple },
    { lvl: "6", title: "DPM RETAIL",        sub: "Discretionary portfolio mgmt",     revenue: "2%/20% standard",      license: "CASP full",       c: C.gold },
    { lvl: "7", title: "HEDGE FUND",        sub: "Institutional capital",            revenue: "2/20 + $10M+ AUM",     license: "Offshore + onshore", c: C.red },
  ];

  const lx = 0.9, lw = W - 1.8;
  const ly0 = 1.75, lh = 0.65, lgap = 0.07;
  ladder.forEach((p, i) => {
    const y = ly0 + i * (lh + lgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x: lx, y, w: lw, h: lh,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.3 },
    });
    // Level number badge
    s.addShape(pres.shapes.RECTANGLE, {
      x: lx, y, w: 0.5, h: lh,
      fill: { color: p.c, transparency: 70 }, line: { color: p.c, width: 0 },
    });
    s.addText(p.lvl, {
      x: lx, y: y + 0.05, w: 0.5, h: lh - 0.1,
      fontFace: FONT_H, fontSize: 24, color: p.c, bold: true,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.title, {
      x: lx + 0.65, y: y + 0.12, w: 3.5, h: 0.4,
      fontFace: FONT_H, fontSize: 14, color: C.text, bold: true, margin: 0,
    });
    s.addText(p.sub, {
      x: lx + 0.65, y: y + 0.38, w: 3.5, h: 0.3,
      fontFace: FONT_B, fontSize: 10, color: C.textMid, margin: 0,
    });
    s.addText(p.revenue, {
      x: lx + 4.3, y: y + 0.2, w: 3.5, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.green, bold: true, margin: 0,
    });
    s.addText("REVENUE", {
      x: lx + 4.3, y: y + 0.0, w: 3.5, h: 0.25,
      fontFace: FONT_B, fontSize: 8, color: C.textDim, charSpacing: 3, margin: 0,
    });
    s.addText(p.license, {
      x: lx + 8.0, y: y + 0.2, w: 3.0, h: 0.35,
      fontFace: FONT_B, fontSize: 11, color: C.gold, bold: true, margin: 0,
    });
    s.addText("LICENCE", {
      x: lx + 8.0, y: y + 0.0, w: 3.0, h: 0.25,
      fontFace: FONT_B, fontSize: 8, color: C.textDim, charSpacing: 3, margin: 0,
    });
    s.addText("→", {
      x: lx + lw - 0.5, y: y + 0.15, w: 0.4, h: 0.35,
      fontFace: FONT_H, fontSize: 16, color: p.c,
      align: "center", margin: 0,
    });
  });

  s.addText([
    { text: "12-month target: ", options: { color: C.textMuted } },
    { text: "Levels 2-3 ", options: { color: C.cyan, bold: true } },
    { text: " · 24-month: ", options: { color: C.textMuted } },
    { text: "Level 4-5 ", options: { color: C.purple, bold: true } },
    { text: " · Levels 6-7 are full career bets — not committed.", options: { color: C.textMuted, italic: true } },
  ], {
    x: 0.9, y: 6.9, w: W - 1.8, h: 0.3,
    fontFace: FONT_B, fontSize: 12, align: "center", margin: 0,
  });
}

// =============================================================================
// SLIDE 12 — WHAT MAKES V2 DIFFERENT
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "10  ·  WHAT MAKES V2 DIFFERENT", "Where competitors stop, V2 begins");
  addFooter(s, 12, TOTAL);

  const head = ["", "INDICATORS\n(LuxAlgo, SMRT, ICT)", "SaaS BOTS\n(3Commas, Cryptohopper)", "QUANT FUNDS\n(institutional)", "TRADING BOT V2"];
  const rowsT = [
    ["Backtest reproducible",  "—",         "Marketed",       "Yes",                "Yes — public methodology"],
    ["Walk-forward OOS+friction", "—",      "Rarely",         "Yes",                "Yes — 2 regimes documented"],
    ["No-lookahead audited",   "—",         "—",              "Internal",           "Yes — public audit doc"],
    ["Belief % tracked",       "—",         "—",              "Internal",           "Yes — radical transparency"],
    ["Funding capture",        "—",         "Limited",        "Yes",                "Yes — Hyperliquid native"],
    ["Open source",            "Mixed",     "—",              "—",                  "Partial planned"],
    ["Accessible price",       "$15-30/mo", "$30-100/mo",     "Inaccessible",       "TBD — community first"],
  ];

  const headRow = head.map((c, i) => ({
    text: c,
    options: {
      bold: true,
      color: i === 4 ? "030308" : C.text,
      fill: { color: i === 4 ? C.gold : C.bgPanelHi },
      charSpacing: 2,
      fontFace: FONT_B,
      fontSize: 10,
      align: "center",
      valign: "middle",
    },
  }));

  // Cell coloring helper
  const tableData = [headRow];
  rowsT.forEach((row, ri) => {
    const formattedRow = row.map((cell, ci) => {
      if (ci === 0) {
        return { text: cell, options: { bold: true, color: C.text, fontSize: 11 } };
      }
      let color = C.textMid;
      if (ci === 4) {
        color = (cell === "—" ? C.textDim : C.gold);
      } else {
        color = (cell === "—" ? C.red : C.textMid);
      }
      return { text: cell, options: { color, fontSize: 11, align: "center" } };
    });
    tableData.push(formattedRow);
  });

  s.addTable(tableData, {
    x: 0.9, y: 1.85, w: W - 1.8,
    colW: [3.0, 2.2, 2.2, 2.0, 2.1333],
    fontFace: FONT_B,
    border: { type: "solid", pt: 0.5, color: C.border },
    fill: { color: C.bgPanel },
    rowH: 0.55,
  });

  // Bottom claim
  const yC = 6.4;
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: yC, w: W - 1.8, h: 0.7,
    fill: { color: C.bgPanelHi }, line: { color: C.gold, width: 1 },
  });
  s.addText([
    { text: "POSITIONING  ·  ", options: { bold: true, color: C.gold, charSpacing: 4 } },
    { text: "Indicators give you the chart. SaaS bots give you a service. Quant funds keep you out. V2 gives you the methodology — open, measured, defensible.",
      options: { color: C.text } },
  ], {
    x: 1.1, y: yC + 0.18, w: W - 2.2, h: 0.45,
    fontFace: FONT_B, fontSize: 12, italic: true, margin: 0,
  });
}

// =============================================================================
// SLIDE 13 — RISK-ADJUSTED HONEST NUMBERS
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bg);
  goldRule(s, 0, 0.6, H - 0.6);
  addSlideTitle(s, "11  ·  THE HONEST NUMBERS", "Risk-adjusted, OOS, friction-applied");
  addFooter(s, 13, TOTAL);

  // Two-column: chart-like representation + hard numbers
  // Left: stylized equity curve (cumulative PnL line)
  const lx = 0.9, ly = 1.75, lw = 6.5, lh = 4.5;
  s.addShape(pres.shapes.RECTANGLE, {
    x: lx, y: ly, w: lw, h: lh,
    fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
  });
  s.addText("V1 OOS + FRICTION · STYLIZED EQUITY", {
    x: lx + 0.2, y: ly + 0.2, w: lw - 0.4, h: 0.3,
    fontFace: FONT_B, fontSize: 10, color: C.gold, charSpacing: 4, margin: 0,
  });

  // Stylized equity curve via line segments (deterministic pseudo-random walk going up)
  const points = 30;
  const cx0 = lx + 0.4, cy0 = ly + 3.8, cxw = lw - 0.8, cyh = 2.8;
  let cyPrev = cy0;
  let cumGain = 0;
  for (let i = 0; i < points; i++) {
    const x1 = cx0 + (i / points) * cxw;
    const x2 = cx0 + ((i + 1) / points) * cxw;
    // Slight pseudo-random walk biased upward
    const noise = (Math.sin(i * 0.7) + Math.cos(i * 1.3)) * 0.15;
    const drift = -0.07; // negative because y increases downward
    cumGain += drift + noise;
    const y1 = cyPrev;
    const y2 = Math.min(cy0, cy0 + cumGain);
    s.addShape(pres.shapes.LINE, {
      x: x1, y: y1, w: x2 - x1, h: y2 - y1,
      line: { color: C.green, width: 2 },
    });
    cyPrev = y2;
  }
  // Baseline
  s.addShape(pres.shapes.LINE, {
    x: cx0, y: cy0, w: cxw, h: 0,
    line: { color: C.textDim, width: 0.5, dashType: "dash" },
  });
  // Y-axis label
  s.addText("PnL +", {
    x: lx + 0.2, y: ly + 0.7, w: 1, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted, margin: 0,
  });
  s.addText("0", {
    x: lx + 0.2, y: cy0 - 0.15, w: 0.4, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted, margin: 0,
  });
  s.addText("2024", {
    x: cx0, y: ly + lh - 0.4, w: 1, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted, margin: 0,
  });
  s.addText("2025", {
    x: cx0 + cxw - 1, y: ly + lh - 0.4, w: 1, h: 0.3,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted, align: "right", margin: 0,
  });

  s.addText("Illustrative — actual equity curves in results/walkforward_v1_oos_friction_*.json", {
    x: lx + 0.2, y: ly + lh - 0.65, w: lw - 0.4, h: 0.25,
    fontFace: FONT_B, fontSize: 8, color: C.textDim, italic: true, margin: 0,
  });

  // Right column: 4 metric panels
  const rx = 7.7, rgap = 0.15, mw = 5.0, mh = 1.0;
  const metrics = [
    { label: "WIN RATE",    a: "60.5%",  b: "49.5%",   c: C.green, note: "in-sample → OOS+friction" },
    { label: "PROFIT FACTOR", a: "3.84",  b: "2.09",   c: C.green, note: "weighted across 2 regimes" },
    { label: "Σ PnL",       a: "+501 pp", b: "+216 pp", c: C.gold, note: "raw IS vs OOS combined" },
    { label: "DRAWDOWN",    a: "~7%",    b: "10.4%",   c: C.cyan, note: "max OOS+friction" },
  ];
  metrics.forEach((m, i) => {
    const y = 1.75 + i * (mh + rgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x: rx, y, w: mw, h: mh,
      fill: { color: C.bgPanel }, line: { color: C.border, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: rx, y, w: 0.05, h: mh,
      fill: { color: m.c }, line: { color: m.c, width: 0 },
    });
    s.addText(m.label, {
      x: rx + 0.2, y: y + 0.1, w: mw - 0.4, h: 0.3,
      fontFace: FONT_B, fontSize: 9, color: C.textMuted, charSpacing: 3, margin: 0,
    });
    s.addText(m.a, {
      x: rx + 0.2, y: y + 0.35, w: 2, h: 0.5,
      fontFace: FONT_H, fontSize: 22, color: C.textDim,
      bold: true, strike: false, margin: 0,
    });
    s.addText("→", {
      x: rx + 2.0, y: y + 0.35, w: 0.5, h: 0.5,
      fontFace: FONT_H, fontSize: 18, color: C.gold,
      align: "center", margin: 0,
    });
    s.addText(m.b, {
      x: rx + 2.5, y: y + 0.35, w: 2, h: 0.5,
      fontFace: FONT_H, fontSize: 22, color: m.c, bold: true, margin: 0,
    });
    s.addText(m.note, {
      x: rx + 0.2, y: y + 0.78, w: mw - 0.4, h: 0.25,
      fontFace: FONT_B, fontSize: 8, color: C.textDim, italic: true, margin: 0,
    });
  });

  // Bottom: the honest stance
  s.addText("The grey number on the left is what most retail bots advertise. The colored number on the right is what V2 acknowledges as real.", {
    x: 0.9, y: 6.5, w: W - 1.8, h: 0.5,
    fontFace: FONT_B, fontSize: 12, color: C.textMid,
    italic: true, align: "center", margin: 0,
  });
}

// =============================================================================
// SLIDE 14 — CLOSING / THE PROMISE
// =============================================================================
{
  const s = pres.addSlide();
  bg(s, C.bgDeep);

  // Subtle background motifs
  drawCandlestickMotif(s, 0, H - 2.5, W, 2, { transparency: 92 });
  drawSignalLine(s, 0, 1.3, W, 1.5, C.gold, { transparency: 80, segments: 100, width: 0.7 });
  drawSignalLine(s, 0, 1.5, W, 1.3, C.cyan, { transparency: 85, segments: 80, width: 0.5 });

  // Side rules
  goldRule(s, 0.7, 1.0, H - 1.5, { width: 0.04 });
  goldRule(s, W - 0.75, 1.0, H - 1.5, { width: 0.02, color: C.cyan, transparency: 40 });

  s.addText("THE PROMISE", {
    x: 1.0, y: 1.3, w: 11.5, h: 0.5,
    fontFace: FONT_B, fontSize: 12, color: C.gold,
    bold: true, charSpacing: 10, margin: 0,
  });

  s.addText("If V2 works, you'll know why.", {
    x: 1.0, y: 2.0, w: 11.5, h: 1.0,
    fontFace: FONT_H, fontSize: 44, color: C.text, bold: true, margin: 0,
  });
  s.addText("If V2 fails, you'll know why.", {
    x: 1.0, y: 3.0, w: 11.5, h: 1.0,
    fontFace: FONT_H, fontSize: 44, color: C.cyan, bold: true, margin: 0,
  });
  s.addText("Either way, we measure, we report, we adapt.", {
    x: 1.0, y: 4.2, w: 11.5, h: 0.7,
    fontFace: FONT_H, fontSize: 22, color: C.textMid,
    italic: true, margin: 0,
  });

  // 3 closing checkpoints
  const cps = [
    { d: "21 May",  e: "Daemon launched · paper trading begins" },
    { d: "28 May",  e: "Intermediate report · J+8 review" },
    { d: "3 June",  e: "Return · full debrief · Phase 2 decision" },
  ];
  const ckw = 4.0, ckh = 1.1, ckgap = 0.2, cky = 5.5;
  const cktw = cps.length * ckw + (cps.length - 1) * ckgap;
  const cksx = (W - cktw) / 2;
  cps.forEach((c, i) => {
    const x = cksx + i * (ckw + ckgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cky, w: ckw, h: ckh,
      fill: { color: C.bgPanel }, line: { color: C.gold, width: 0.5 },
    });
    s.addText(c.d, {
      x: x + 0.2, y: cky + 0.15, w: ckw - 0.4, h: 0.4,
      fontFace: FONT_H, fontSize: 18, color: C.gold, bold: true, margin: 0,
    });
    s.addText(c.e, {
      x: x + 0.2, y: cky + 0.55, w: ckw - 0.4, h: 0.5,
      fontFace: FONT_B, fontSize: 11, color: C.text, margin: 0,
    });
  });

  s.addText("Trading Bot V2  ·  Pitch & Philosophy  ·  May 2026  ·  Prepared for Badoun", {
    x: 1.0, y: H - 0.4, w: 11.5, h: 0.25,
    fontFace: FONT_B, fontSize: 9, color: C.textMuted,
    charSpacing: 6, margin: 0,
  });
}

// ---------------------------------------------------------------------------- Write
pres.writeFile({ fileName: "/sessions/wizardly-gifted-hypatia/mnt/trading-bot-v2/Trading_Bot_V2_Pitch_Deck.pptx" })
  .then(p => console.log("Wrote:", p))
  .catch(e => { console.error(e); process.exit(1); });
