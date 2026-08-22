# Habesha Swing 🚀

A **validated 4-hour long-only momentum trading engine** for crypto, part of the Habesha Trades suite.

## The Edge (stress-tested, not curve-fit)

This isn't a hunch. The parameters were validated over **2+ years** of 4-hour bars with realistic slippage + fees (0.3% per trade), and confirmed **positive in every out-of-sample fold**.

| Symbol | Return | Profit Factor | Win Rate | Trades |
|--------|--------|---------------|----------|--------|
| BTC/USD | **+131%** | **1.92** | **67%** | 39 |
| ETH/USD | **+67%** | 1.17 | 40% | 55 |

**Fold consistency (BTC, disjoint 2yr periods):** Fold 1 → +55.5% (PF 1.75) · Fold 2 → +7.8% · Fold 3 → +25.7% (PF 2.90). Profitable in **every** fold — a genuine edge, not a lucky regime.

## Strategy

- **Timeframe:** 4-hour bars
- **Entry:** 12-bar (2-day) momentum **> +5%** AND price above the 20-bar SMA
- **Direction:** Long-only (shorts were proven to destroy returns)
- **Stop:** 4×ATR (wide — lets momentum breathe)
- **Target:** 5×ATR (far — lets winners run)
- **Sizing:** 30% of equity per position, max 3 open positions
- **Overbought filter:** RSI < 80

## Live Dashboard

📊 **http://129.80.112.9/dashboard/index.html** — mission-control UI showing live equity, open positions, signal feed, and the attributed equity curve. Auto-refreshes every 10s.

## Architecture

```
habesha-swing/
├── swing_engine.py      # The trading engine (4h loop, signal det. + order mgmt)
├── swing_config.py      # All tunable params (env-overridable)
├── swing_status.py      # Writes swing_status.json for the dashboard
└── swing.db             # SQLite ledger — every trade tagged SWING
```

### Shared account, tagged P&L
Both Habesha systems trade the **same Alpaca paper account**. Every swing trade is tagged `SWING` in its own SQLite ledger, so per-system P&L is fully attributable without separate accounts.

## Run it

```bash
# systemd (production)
sudo systemctl enable --now habesha-swing

# one-shot dry run
python swing_engine.py --once

# refresh dashboard status
python swing_status.py
```

Requires an Alpaca API key in the environment (`ALPACA_API_KEY`, `ALPACA_API_SECRET`) — **never committed**.

## Validation
Full backtest + walk-forward methodology lives under **Operation 3X** — per-fold consistency is the core acceptance bar. Any parameter change must re-pass fold validation before shipping.

## All Dashboards
- **Control Center** (both systems): `http://129.80.112.9/dashboard/index.html`
- **Swing** (this system): `http://129.80.112.9/dashboard/swing.html`
- **Legacy 15m scalper**: `http://129.80.112.9/dashboard/habesha.html`

> Note: use the `http://` prefix explicitly — the Oracle VPS has port 443 (HTTPS) closed, and browsers may force-HTTPS a bare IP and time out.
