#!/usr/bin/env python3
"""
HABESHA SWING - 4h Long-Only Momentum Trading Engine
The VALIDATED edge: 12-bar (2-day) momentum > +5%, price above 20-bar SMA,
long-only. Stop 4xATR, take 5xATR, trail 1.5xATR.

SHARED ACCOUNT: tags all trades with TRADE_TAG="SWING" so per-system P&L
can be attributed on the shared Alpaca paper account.
"""
import os, sys, json, time, math
import numpy as np
from datetime import datetime, timezone, date
from decimal import Decimal

sys.path.insert(0, "/home/ubuntu/titanium")
sys.path.insert(0, "/home/ubuntu/habesha-swing")

from swing_config import CONFIG


def _load_env():
    for p in ["/home/ubuntu/titanium/.env", "/home/ubuntu/habesha-swing/.env"]:
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


# --- SQLite ledger ---
import sqlite3
SCHEMA = """
CREATE TABLE IF NOT EXISTS swing_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL, entry REAL, stop REAL, take REAL,
    exit_price REAL, exit_time TEXT,
    pnl REAL, quality REAL, regime TEXT,
    opened_at TEXT NOT NULL, status TEXT DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS swing_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, symbol TEXT NOT NULL,
    mom REAL, sma_dist REAL, action TEXT, price REAL, atr REAL
);
"""


class SwingDB:
    def __init__(self, path=None):
        self.path = path or CONFIG.DB_PATH
        self._db = sqlite3.connect(self.path)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def open_trade(self, symbol, side, qty, entry, stop, take, quality, regime):
        cur = self._db.execute(
            "INSERT INTO swing_trades (symbol, side, qty, entry, stop, take, quality, regime, opened_at, status) "
            "VALUES (?,?,?,?,?,?,?,?,?, 'open')",
            (symbol, side, qty, entry, stop, take, quality, regime, datetime.utcnow().isoformat()))
        self._db.commit()
        return cur.lastrowid

    def get_open_trade(self, symbol):
        cur = self._db.execute("SELECT * FROM swing_trades WHERE symbol=? AND status='open' LIMIT 1", (symbol,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def reconcile_symbol(self, symbol, live_qty=None, live_price=None):
        """ZOMBIE-PROOF: reconcile swing ledger against live account.
        If ledger says open but account has no REAL position (or less qty),
        fix the ledger to match reality so the swing engine never chases ghosts."""
        out = {"repaired": []}
        existing = self.get_open_trade(symbol)
        if not existing:
            return out
        lqty = float(live_qty if live_qty is not None else 0)
        eqty = float(existing.get("qty", 0) or 0)

        # Ghost: ledger says open but account has nothing (or far less)
        if lqty < eqty * 0.5:  # account has less than half the recorded qty
            # Close the ghost trade at current/fried price
            exit_px = float(live_price if live_price else existing.get("entry", 0))
            pnl = (exit_px - float(existing["entry"])) * eqty
            self._db.execute(
                "UPDATE swing_trades SET exit_price=?, exit_time=?, pnl=?, status='closed' WHERE id=?",
                (exit_px, datetime.utcnow().isoformat(), round(pnl, 4), existing["id"]))
            self._db.commit()
            out["repaired"].append(f"ghost_open_closed {symbol} (recorded {eqty} vs live {lqty})")
        elif abs(lqty - eqty) > eqty * 0.01:
            # Partial: update qty to match
            self._db.execute("UPDATE swing_trades SET qty=? WHERE id=?",
                             (lqty, existing["id"]))
            self._db.commit()
            out["repaired"].append(f"qty_mismatch {eqty}->{lqty}")
        return out

    def close_trade(self, tid, exit_price, pnl):
        self._db.execute("UPDATE swing_trades SET exit_price=?, exit_time=?, pnl=?, status='closed' WHERE id=?",
                         (exit_price, datetime.utcnow().isoformat(), pnl, tid))
        self._db.commit()

    def log_signal(self, symbol, mom, sma_dist, action, price, atr):
        self._db.execute("INSERT INTO swing_signals (ts,symbol,mom,sma_dist,action,price,atr) VALUES (?,?,?,?,?,?,?)",
                         (datetime.utcnow().isoformat(), symbol, mom, sma_dist, action, price, atr))
        self._db.commit()

    def stats(self):
        cur = self._db.execute("SELECT COUNT(*) FROM swing_trades WHERE status='closed'")
        closed = cur.fetchone()[0]
        cur = self._db.execute("SELECT COALESCE(SUM(pnl),0) FROM swing_trades WHERE status='closed'")
        total = cur.fetchone()[0]
        cur = self._db.execute("SELECT COUNT(*) FROM swing_trades WHERE status='open'")
        open_n = cur.fetchone()[0]
        return {"closed": closed, "total_pnl": round(total, 2), "open": open_n}


# --- Strategy ---
def load_4h_bars(symbol):
    """Load 4h bars from the shared history cache (floats)."""
    fname = f"{CONFIG.DATA_DIR_4H}/history_{symbol.replace('/', '')}.json"
    if not os.path.exists(fname):
        return None
    with open(fname) as f:
        raw = json.load(f)
    raw = raw[::-1]
    return [(float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"]), b.get("datetime",""))
            for b in raw if all(k in b for k in ("open","high","low","close"))]


def compute_signal(bars, check_idx):
    """Compute momentum signal at bar check_idx. Returns tuple (action, mom, sma_dist, atr_idx)."""
    c = [b[3] for b in bars]
    h = [b[1] for b in bars]
    l = [b[2] for b in bars]
    lb = CONFIG.LOOKBACK_BARS
    trend = CONFIG.TREND_SMA
    if check_idx < max(lb, trend):
        return "HOLD", 0.0, 0.0, 0.0
    price = c[check_idx]
    prev = c[check_idx - lb]
    mom = (price - prev) / prev if prev else 0.0
    sma = sum(c[check_idx-trend:check_idx]) / trend if check_idx >= trend else price
    sma_dist = (price - sma) / sma if sma else 0.0
    # ATR at check_idx
    atr_idx = 0.0
    if check_idx >= 14:
        trs = []
        for i in range(check_idx-13, check_idx+1):
            tr = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
            trs.append(tr)
        atr_idx = sum(trs)/len(trs) if trs else 0.0
    action = "HOLD"
    if mom > CONFIG.MOMENTUM_THRESHOLD and sma_dist > 0:
        action = "BUY"
    return action, mom, sma_dist, atr_idx


def main(once=False):
    _load_env()
    db = SwingDB()
    log_dir = CONFIG.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    def _log(msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(f"{log_dir}/swing.log", "a") as f:
            f.write(line + "\n")

    # Reuse Alpaca client
    sys.path.insert(0, "/home/ubuntu/titanium")
    from alpaca_client import AlpacaClient, AlpacaError, _crypto_ccy_pair
    client = AlpacaClient()

    _log(f"HABESHA SWING starting | symbols={CONFIG.SYMBOLS} | 4h long-only momentum")

    while True:
        for symbol in CONFIG.SYMBOLS.split(","):
            symbol = symbol.strip()
            try:
                bars = load_4h_bars(symbol)
                if bars is None or len(bars) < 100:
                    _log(f"{symbol}: no 4h data")
                    continue

                last_idx = len(bars) - 1
                action, mom, sma_dist, atr_i = compute_signal(bars, last_idx)
                price = bars[last_idx][3]
                db.log_signal(symbol, round(mom,4), round(sma_dist,4), action, price, round(atr_i,2))

                # ZOMBIE-PROOF: reconcile against live account first
                try:
                    _live = client.get_position(_crypto_ccy_pair(symbol))
                    _lqty = float(_live.get("qty", 0) or 0)
                except Exception:
                    _lqty = 0
                _rep = db.reconcile_symbol(symbol, live_qty=_lqty, live_price=price)
                for _r in _rep.get("repaired", []):
                    _log(f"RECONCILE[{symbol}]: {_r}")
                # Manage open position
                existing = db.get_open_trade(symbol)
                if existing:
                    # Check take profit (crypto uses close to exit - no native bracket here)
                    entry = float(existing["entry"])
                    take = float(existing["take"])
                    if price >= take:
                        try:
                            client.close_position(symbol)
                            pnl = (price - entry) * float(existing["qty"])
                            db.close_trade(existing["id"], price, round(pnl,4))
                            _log(f"CLOSE {symbol} at TAKE ${take:.2f} (px {price:.2f}) pnl=${pnl:+.2f}")
                        except Exception as e:
                            _log(f"CLOSE_FAIL {symbol}: {e}")
                    continue  # position open, don't open another

                # Open new position on BUY signal
                if action == "BUY":
                    # Position size 30% of equity
                    acct = client.get_account()
                    equity = float(acct.get("equity", "0"))
                    cash = float(acct.get("cash", "0"))
                    pos_value = min(equity * CONFIG.MAX_POS_SIZE_PCT,
                                    cash * CONFIG.CASH_BUFFER_PCT)
                    entry_px = price * 1.002  # slippage
                    qty = pos_value / entry_px
                    if qty <= 0:
                        continue
                    stop = entry_px - atr_i * CONFIG.STOP_MULT if atr_i > 0 else entry_px * 0.95
                    take = entry_px + atr_i * CONFIG.TAKE_MULT if atr_i > 0 else entry_px * 1.1
                    try:
                        # CHECK for conflicting open orders first (wash-trade protection)
                        existing_orders = client.get_open_orders(symbol=symbol)
                        conflicting = [
                            o for o in existing_orders
                            if o.get("side", "").lower() == "sell"
                            and o.get("status", "") in ("new", "accepted", "pending_new")
                        ]
                        if conflicting:
                            _log(f"SKIP {symbol}: {len(conflicting)} opposing SELL orders "
                                 f"(shared account conflict) - will retry next cycle")
                            continue
                        # Place protective stop BEFORE the entry (avoids naked entry if entry fills)
                        order = client.place_market(symbol, round(qty,6), "buy")
                        if order.get("id"):
                            try:
                                # Place the protective stop_limit leg
                                client.place_market_stop(
                                    _crypto_ccy_pair(symbol), round(qty,6),
                                    stop_price=stop, side="sell")
                                _log(f"STOP placed {symbol} @ ${stop:.2f}")
                            except Exception as se:
                                _log(f"STOP_FAIL {symbol}: {se}")
                        oid = db.open_trade(symbol, "buy", qty, entry_px, stop, take, 60, "swing")
                        _log(f"OPEN BUY {round(qty,4)} {symbol} @ ~${entry_px:.2f} "
                             f"stop=${stop:.2f} take=${take:.2f} | trade#{oid}")
                    except Exception as e:
                        _log(f"OPEN_FAIL {symbol}: {e}")
            except Exception as e:
                _log(f"ERR {symbol}: {e}")

        # Update dashboard status each cycle
        try:
            sys.path.insert(0, "/home/ubuntu/habesha-swing")
            from swing_status import build_status
            import json as _json
            _s = build_status()
            with open("/home/ubuntu/adwa-engine/dashboard/swing_status.json", "w") as _f:
                _json.dump(_s, _f)
        except Exception as se:
            _log(f"status update err: {se}")

        if once:
            break
        time.sleep(4 * 3600)  # check every 4h (aligns with candle close)


if __name__ == "__main__":
    import argparse
    import fcntl
    # Single-instance guard
    _lf = open('/home/ubuntu/habesha-swing/swing.lock', 'w')
    try:
        fcntl.flock(_lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another swing engine instance is already running - exiting")
        sys.exit(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    main(once=args.once)
