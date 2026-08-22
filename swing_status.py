"""HABESHA SWING - writes swing_status.json for the dashboard."""
import os, json, sqlite3
from datetime import datetime
from swing_config import CONFIG


def build_status():
    db_path = CONFIG.DB_PATH
    status = {
        "updated": datetime.utcnow().isoformat(),
        "service": "active",
        "engine": "SWING",
        "timeframe": "4h",
        "edge": "12-bar momentum >5% + above 20-SMA, long-only",
        "current": {},
        "trades": {"total": 0, "open": 0, "closed": 0, "pnl": 0},
        "equity_curve": [],
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
