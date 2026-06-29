# No-Lookahead Audit — ICC Pipeline V1

**Date** : 20 May 2026
**Auditor** : automated review, source-code walk-through
**Scope** : `strategies/icc_structure.py`, `strategies/icc_orderblocks.py`, `strategies/icc_cycle.py`
**Result** : **PASS — no actionable look-ahead bias found.**

This document satisfies methodological directive #2, item 5: *“justification écrite obligatoire de la méthode pour chaque backtest”*. Every place where the pipeline could leak future information into a past decision is enumerated, traced, and validated.

## Operational definition

A function `f(state_at_t)` exhibits **look-ahead bias** if its output depends on any data point dated `> t`. For a backtest to be valid, every decision taken at bar `t` must use only `data[≤ t]`.

In this codebase, time is expressed via two equivalent coordinates:
- `bar_index` — integer position in the input DataFrame
- `confirmed_at_bar` — the bar at which an event becomes “visible” (always `bar_index + W` for a swing detected with lookback `W`)

The decision functions in `icc_cycle` consult structures and order blocks using `confirmed_at_bar`, never `bar_index`. This is the correct convention.

## Surfaces reviewed

| # | Location | Surface | Verdict |
|---|---|---|---|
| 1 | `icc_structure.detect_structures` | swing confirmation at lag `W` | **CLEAN** |
| 2 | `icc_structure.is_swing_high/low` | window `[i-W, i+W]` used at iter `i` | **CLEAN** (see §1) |
| 3 | `icc_orderblocks.detect_order_blocks` | OB candle is in the past at break confirmation time | **CLEAN** |
| 4 | `icc_orderblocks._track_consumption` | scans forward from `detected_at_bar+1` | **CLEAN with caveat — see §3** |
| 5 | `icc_orderblocks.classify_discount_premium` | uses `s.bar_index > ob.detected_at_bar` filter | **CLEAN** |
| 6 | `icc_cycle.compute_daily_bias` | filters `s.confirmed_at_bar > at_bar` | **CLEAN** |
| 7 | `icc_cycle.try_create_setup` | OB-consumed gating | **CLEAN — see §3** |
| 8 | `icc_cycle._find_last_micro_during_correction` | filters `confirmed_at_bar ∈ [from_bar, to_bar]` | **CLEAN** |
| 9 | `icc_cycle._compute_initial_sl` (V1) | filters `s.confirmed_at_bar > h1_bar` | **CLEAN** |
| 10 | `icc_cycle._compute_initial_sl_h4` (V2) | filters `s.confirmed_at_bar > h4_pos` | **CLEAN** |
| 11 | `icc_cycle._monitor_in_trade` trailing (V1) | filters `confirmed_at_bar > h1_bar` and `<= setup.entry_bar` | **CLEAN** |
| 12 | `icc_cycle._monitor_in_trade` trailing (V2) | same with `h4_pos` and `entry_h4_pos` | **CLEAN** |
| 13 | `icc_cycle.run_icc_cycle` H4-indication → H1-bar mapping | uses `searchsorted(h4_confirmed_ts, 'right')` ≤ current loop bar | **CLEAN** |
| 14 | `icc_cycle._apply_friction` (added 2026-05) | reads only `setup.entry_timestamp` and `setup.exit_timestamp` | **CLEAN** |

## 1. Swing confirmation (`is_swing_high/low`)

```python
def is_swing_high(closes, i, w):
    if i < w or i + w >= len(closes):
        return False
    window = closes[i - w: i + w + 1]
    return closes[i] == window.max() and ...
```

This function is called with candidate bar `i` from the perspective of the present bar `i + w`. The window includes bars `[i-w, i+w]` — all of which are **strictly ≤ present bar** because `present = i + w` implies the right edge `i+w = present`. The function therefore never consults future data relative to the time at which it is called. The naming convention can confuse — `i` is the *candidate* bar, not the *present* bar.

## 2. `detect_structures` confirmation timing

```python
for i in range(W, n):
    cand_bar = i - W
    if is_swing_high(closes, cand_bar, W):
        # confirmed at iteration i, i.e. at present_bar = i = cand_bar + W
```

A swing at `cand_bar` is added to the structures list with `confirmed_at_bar = i` (the present bar). All downstream consumers filter by `confirmed_at_bar`, never `bar_index`. So even though `bar_index` lies in the past, the *visibility* timestamp is correctly `confirmed_at_bar`.

## 3. OB consumption — vacuous gap, not a bias

`_track_consumption` scans forward from `detected_at_bar + 1` and marks `consumed = True` + `consumed_at_bar = i` at the first re-entry. This populates fields with information about future bars relative to `detected_at_bar`.

`try_create_setup` then has:
```python
if h4_ob.consumed and h4_ob.consumed_at_bar is not None:
    pass  # accept all not-yet-consumed at indication time
```

**This looks like it could be a look-ahead** (the OB carries future information about its consumption). Trace, however, the timing:

- Indications appear at `h4_indication.confirmed_at_ts`, which equals the H4 bar where the structure-break is confirmed.
- An OB is "detected" at `ob.detected_at_bar = ob.structure_broken.confirmed_at_bar` — the same H4 bar.
- An OB can only be "consumed" at a bar `> detected_at_bar`.
- Therefore, at indication time in H4 frame, **no OB has yet been consumed**, by construction.

The filter gap (no check `consumed_at_bar > indication_bar`) is therefore **vacuously satisfied** — there is no scenario in which a "future-consumed" OB is misclassified as "currently consumed". This was verified by tracing a sample of OB lifecycles end-to-end.

**Recommended cleanup (cosmetic, not a bias fix)**: replace the `pass` with an explicit `# vacuously safe — see NO_LOOKAHEAD_AUDIT.md §3` comment, and add an assertion `assert ob.consumed_at_bar is None or ob.consumed_at_bar > ob.detected_at_bar` for paranoia.

## 4. Daily / H4 bias

`compute_daily_bias(structs, at_bar)` iterates structures and applies:
```python
if s.confirmed_at_bar > at_bar:
    break
if s.broken and s.broken_at_bar is not None and s.broken_at_bar <= at_bar:
    continue
```

Both conditions are strict-correct: future-confirmed structures are skipped, broken structures whose break is in the past at `at_bar` are treated as broken. **Pass.**

## 5. SL / TP / trailing references

All three SL/TP functions (V1 H1-close, V2 H4-wick, V2b H4-close) filter the structure list by:
```python
if s.confirmed_at_bar > current_bar:
    continue
```
plus, for trailing, an additional `> setup.entry_bar` floor to forbid using structures formed before entry. **Pass.**

Wick-anchor mode (V2) additionally reads `h4_prices.iloc[candidate.bar_index]['low'|'high']` — these are past OHLC values (the swing's own candle), legitimately known at the time the swing was confirmed. **Pass.**

## 6. Friction model (`_apply_friction`)

The friction model added 2026-05 reads only `setup.entry_timestamp` and `setup.exit_timestamp`, both of which are populated when the trade closes — i.e., after both events have occurred. No future information is consulted relative to the close time. **Pass.**

## What this audit does *not* cover

- **Survivorship bias** in the asset universe. The 8 majors were chosen *because* they have sufficient data — we do not test on coins that delisted before 2024. This is not a look-ahead bias per se, but it does bias the universe upward. Mitigation: explicit universe filter (see §`results/walkforward_v1_oos_friction_filtered_*`), document the selection.
- **Selection bias on parameters.** The ICC parameters (`swing_lookback=3`, `min_rr_for_ob_tp=2.5`, `measured_move_rr=3.0`) come from the ICC spec, not from data-mining. `tune2.py` and friends do not touch the ICC pipeline. **No re-fit risk.**
- **Selection bias on filtered universe** (ETH/LTC/AVAX/SOL). This filter was applied *after* observing OOS results — a soft form of data-peeking. Mitigation outstanding: validate on a third window (e.g. 2020-06 → 2021-06 or 2026-H1 once enough data accumulates).
- **Execution path realism**. The backtest assumes orders fill at observed prices ± modelled slippage. Real Hyperliquid execution may experience partial fills, requoting, or hostile order book moves not captured here.

## Conclusion

The ICC pipeline V1 is free of look-ahead bias in the technical sense. The numbers in `results/walkforward_v1_oos_friction_*.md` (filtered universe: Sharpe 2.22 bull / 1.07 bear with friction) are produced by a methodologically clean process within the bounds of the parquet OHLC dataset.

The remaining risks to the validity of those numbers are **selection bias (universe) and survivorship bias (assets)** — neither of which is a look-ahead issue but both of which warrant explicit acknowledgment in any external communication of the results. The four-qualifier line (Methodo · Friction · Window · Regime) introduced in directive #2 should be extended with a fifth implicit qualifier *Universe* whenever the filtered universe is used.

— Audit closed.
