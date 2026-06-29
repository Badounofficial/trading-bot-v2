#!/bin/bash
# verify_session_4.sh — Validation complète Session 4 en 1 commande
# Usage: bash scripts/verify_session_4.sh

set -e

echo "===================================================================="
echo "  Trading Bot v2 — Session 4 Verification"
echo "===================================================================="
echo ""

# ── Step 1: Repo location check ──
echo "── Step 1/5: Repo location ──"
if [ ! -f "strategies/icc_cycle.py" ]; then
    echo "  ❌ Run this script from ~/Desktop/trading-bot-v2/"
    exit 1
fi
echo "  ✓ In correct directory"
echo ""

# ── Step 2: Python syntax ──
echo "── Step 2/5: Python syntax check ──"
python -c "import ast; ast.parse(open('strategies/icc_cycle.py').read())" \
    && echo "  ✓ strategies/icc_cycle.py" \
    || (echo "  ❌ Syntax error in icc_cycle.py"; exit 1)
python -c "import ast; ast.parse(open('tests/test_icc_cycle.py').read())" \
    && echo "  ✓ tests/test_icc_cycle.py" \
    || (echo "  ❌ Syntax error in test_icc_cycle.py"; exit 1)
echo ""

# ── Step 3: Import check (catches missing fields, wrong imports) ──
echo "── Step 3/5: Import check ──"
python -c "
from strategies.icc_cycle import (
    TradeSetup, TradeState, Direction, BiasState, TradeMode, ExitReason,
    compute_daily_bias, try_create_setup, update_setup_state,
    _close_setup, _monitor_in_trade,
    _compute_initial_sl, _compute_initial_tp,
)
# Verify new ExitReasons exist
assert ExitReason.TRAILING_HIT.value == 'TRAILING_HIT'
assert ExitReason.PARTIAL_TP_HIT.value == 'PARTIAL_TP_HIT'
print('  ✓ All imports OK')
print('  ✓ TRAILING_HIT enum present')
print('  ✓ PARTIAL_TP_HIT enum present')
" || (echo "  ❌ Import or enum check failed"; exit 1)
echo ""

# ── Step 4: Run all ICC tests (Sessions 2, 3, 4) ──
echo "── Step 4/5: Run all ICC test suites ──"
echo ""
echo "  → Session 2 (Structure):"
python -m pytest tests/test_icc_structure.py -q --tb=line 2>&1 | tail -3
echo ""
echo "  → Session 3 (Order Blocks):"
python -m pytest tests/test_icc_orderblocks.py -q --tb=line 2>&1 | tail -3
echo ""
echo "  → Session 4 (Cycle):"
python -m pytest tests/test_icc_cycle.py -q --tb=short 2>&1 | tail -10
echo ""

# ── Step 5: Run baseline validation on BTC ──
echo "── Step 5/5: Baseline regression check on BTC ──"
echo "  (Verifying CONFIG A still produces same results as before refactor)"
python scripts/compare_icc_configs.py BTC 2>&1 | tail -20 || \
    echo "  ⚠ compare_icc_configs.py failed — investigate manually"
echo ""

echo "===================================================================="
echo "  ✓ Session 4 verification complete"
echo "===================================================================="
echo ""
echo "  Next steps if all green:"
echo "    1. Update docs/JOURNAL.md with Session 4 entry"
echo "    2. Create docs/RECAPS/SESSION_4_RECAP.md"
echo "    3. Create docs/RECAPS/AUDIT_SESSION_4.md"
echo "    4. git commit + bash scripts/backup.sh"
echo ""
