#!/usr/bin/env bash
# Convert the apprentissage dossier markdown to a PDF via pandoc + LaTeX or weasyprint
# Falls back to HTML+wkhtmltopdf-equivalent if LaTeX is missing.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IN="$ROOT/Trading_Bot_V2_Apprentissage_Dossier.md"
OUT="$ROOT/Trading_Bot_V2_Apprentissage_Dossier.pdf"

# Try pandoc with default PDF engine (will use latex if available)
if pandoc --list-output-formats 2>/dev/null | grep -q pdf; then
  echo "[build_dossier_pdf] trying pandoc → PDF (LaTeX engine)"
  pandoc "$IN" \
    -o "$OUT" \
    --toc --toc-depth=2 \
    --number-sections \
    -V geometry:margin=1in \
    -V fontsize=11pt \
    -V mainfont="Helvetica" \
    -V documentclass=article \
    -V colorlinks=true \
    -V linkcolor=blue \
    -V urlcolor=blue \
    --metadata title="Trading Bot V2 — Dossier d'apprentissage" \
    --metadata author="Préparé pour Badoun" \
    --metadata date="21 mai 2026" 2>&1
  if [ -f "$OUT" ]; then
    echo "[build_dossier_pdf] OK → $OUT"
    exit 0
  fi
fi

echo "[build_dossier_pdf] pandoc PDF engine missing or failed, falling back to HTML→PDF via LibreOffice"

HTML="$ROOT/_dossier_tmp.html"
pandoc "$IN" -o "$HTML" --standalone --toc --toc-depth=2 \
  --metadata title="Trading Bot V2 — Dossier d'apprentissage" \
  -V lang=fr \
  -c <(cat <<'CSS'
body { font-family: -apple-system, Helvetica, Arial, sans-serif; line-height: 1.5; max-width: 760px; margin: 2em auto; color: #111; padding: 0 1em; }
h1 { font-size: 26pt; border-bottom: 2px solid #d4af37; padding-bottom: 0.3em; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 18pt; color: #1a2a45; margin-top: 1.5em; }
h3 { font-size: 14pt; color: #444; }
code, pre { font-family: 'SF Mono', Consolas, monospace; background: #f6f6f6; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.92em; }
pre { padding: 0.8em; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left; }
th { background: #f0f0f0; }
blockquote { border-left: 3px solid #d4af37; padding-left: 1em; color: #555; }
a { color: #1a5fb4; text-decoration: none; }
@page { margin: 2cm; }
CSS
) 2>&1
soffice --headless --convert-to pdf "$HTML" --outdir "$ROOT" 2>&1
mv "$ROOT/_dossier_tmp.pdf" "$OUT" 2>/dev/null
rm -f "$HTML"

if [ -f "$OUT" ]; then
  echo "[build_dossier_pdf] OK → $OUT"
else
  echo "[build_dossier_pdf] FAILED"
  exit 1
fi
