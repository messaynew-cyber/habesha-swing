"""HABESHA SWING - writes swing_status.json for the dashboard."""
import os, json, sqlite3
from datetime import datetime
from swing_config import CONFIG


def build_status():
    db_path = CONFIG.DB_PATH
    # HEARTBEAT FIX (2026-09-02): heartbeat = the engine's MOST RECENT signal in the
    # swing DB (swing_signals), which the engine writes every 4h cycle (BUY/HOLD/SELL)
    # regardless of market state. The old logic read the last swing.log line, but the
    # engine only logs to swing.log on RESTART - so a healthy long-running engine looked
    # "stale (24h silent)" forever (server up since Sep 1 -> false red banner).
    # If the DB is unreachable, fall back to the log last-line.
    last_hb = None
    _signal_ts = None
    try:
        import sqlite3 as _sq
        _c = _sq.connect(db_path)
        _r = _c.execute("SELECT ts FROM swing_signals ORDER BY id DESC LIMIT 1").fetchone()
        _c.close()
        if _r and _r[0]:
            # DB ts is ISO "YYYY-MM-DDTHH:MM:SS.ffffff" (naive, server=UTC).
            _signal_ts = _r[0][:19].replace("T", " ")
    except Exception:
        _signal_ts = None
    if _signal_ts:
        last_hb = _signal_ts
    if not last_hb:  # fallback: last log line timestamp
        try:
            import re as _re
            _ts_re = _re.compile(r"^(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\])")
            _lines = open("/home/ubuntu/habesha-swing/logs/swing.log").readlines()
            for _line in reversed(_lines):
                _m = _ts_re.match(_line)
                if _m:
                    last_hb = _line[1:20]
                    break
        except Exception:
            pass
    service_state = "stale"
    if last_hb:
        try:
            age_h = (datetime.utcnow() - datetime.strptime(last_hb, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
            service_state = "active" if age_h < 6 else f"stale ({age_h:.0f}h silent)"
        except Exception:
            pass

    status = {
        "updated": datetime.utcnow().isoformat(),
        "last_heartbeat": last_hb,
        "service": service_state,
        "engine": "SWING",
        "timeframe": "4h",
        "edge": "12-bar momentum >5% + above 20-SMA, long-only",
        "current": {},
        "trades": {"total": 0, "open": 0, "closed": 0, "pnl": 0},
    }
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM swing_trades")
            status["trades"]["total"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM swing_trades WHERE status='closed'")
            status["trades"]["closed"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM swing_trades WHERE status='open'")
            status["trades"]["open"] = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(pnl),0) FROM swing_trades WHERE status='closed'")
            status["trades"]["pnl"] = round(cur.fetchone()[0], 2)
            # open positions
            cur.execute("SELECT symbol, side, qty, entry, stop, take, opened_at FROM swing_trades WHERE status='open'")
            for r in cur.fetchall():
                status["current"][r[0]] = {
                    "side": r[1], "qty": r[2], "entry": r[3],
                    "stop": r[4], "take": r[5], "opened_at": r[6]
                }
            # closed trades for equity curve
            cur.execute("SELECT opened_at, pnl FROM swing_trades WHERE status='closed' ORDER BY id")
            cum = 1000.0
            curve = []
            for r in cur.fetchall():
                cum += r[1]
                curve.append({"t": r[0][:16], "e": round(cum, 2)})
            status["equity_curve"] = curve[-60:]
            conn.close()
    except Exception as e:
        status["error"] = str(e)
    # last few signals
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT ts, symbol, mom, action, price FROM swing_signals ORDER BY id DESC LIMIT 12")
            sigs = []
            for r in cur.fetchall():
                sigs.append({"ts": r[0][:16], "symbol": r[1], "mom": r[2],
                             "action": r[3], "price": r[4]})
            status["signals"] = sigs
            conn.close()
    except Exception:
        pass
    return status


if __name__ == "__main__":
    s = build_status()
    out = "/home/ubuntu/adwa-engine/dashboard/swing_status.json"
    with open(out, "w") as f:
        json.dump(s, f, indent=2)
    print(f"wrote {out}: {len(json.dumps(s))} chars")
