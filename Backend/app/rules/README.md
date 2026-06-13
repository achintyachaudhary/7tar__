# Screening Rules

This directory holds the **breakout screening rules** the backend applies. Each rule is a
plain JSON file so you can read exactly what criteria are in effect and tweak them without
touching any Python code. Changes are picked up automatically on the next scan (the loader
re-reads a file whenever it changes on disk — no server restart required).

## Files

| File | Scanner | Timeframe |
| ---- | ------- | --------- |
| `brst_breakout.json` | **BrSt** page | 6 months / daily candles |
| `multi_year_breakout.json` | **Multi Year** page | 3 years / weekly candles (resampled from daily) |

You can view the live, in-effect rules from the API at `GET /api/rules`
(or a single rule at `GET /api/rules/{id}`).

## Rule structure

Every rule file has the same shape:

- **`id` / `name` / `description`** – human-readable summary of what the scanner looks for.
- **`data`** – which price history is loaded (`period`, `interval`, minimum bars). Daily
  volume is always pulled because it is needed for volume confirmation.
- **`resistance`** – how the resistance level and "tests" of that level are detected:
  - `max_distance_from_high_pct` – how close to the period high the current price must be.
  - `test_zone_pct` – how close a candle's high must get to count as a test of resistance.
  - `min_distinct_tests` – minimum number of separate touches of the resistance.
  - `test_grouping_bars` / `test_grouping_weeks` – touches within this many bars count as one.
- **`volume_confirmation`** – the institutional-volume filter inspired by the multi-year
  breakout methodology (a real breakout is backed by volume well above the 50-day average):
  - `average_window_days` – baseline window (default 50 trading days).
  - `recent_lookback_days` – the recent window treated as the "breakout" window.
  - `min_breakout_volume_multiple` – recent volume must be at least this multiple of the
    50-day average to be **volume-confirmed**.
  - `require_for_match` – when `true`, only volume-confirmed candidates are returned; when
    `false` (default) every candidate is returned but tagged with its volume ratio so you
    can sort / filter in the UI.

> Keys starting with `_` (e.g. `_comment`) are documentation only and are ignored by the loader.

## Volume confirmation math

```
baseline_avg = mean(daily_volume over the average_window_days before the recent window)
recent_volume = max(daily_volume over the last recent_lookback_days)
volume_ratio  = recent_volume / baseline_avg
volume_confirmed = volume_ratio >= min_breakout_volume_multiple
```

The 50-day average volume requires **daily** volume data. Fetch it from the **NSE 1Day**
page ("Fetch Volume · Nifty 50" for a quick start, or "Fetch All Stocks" for the whole NSE
universe). The scanners reuse this stored daily volume when present and fall back to a live
download otherwise.
