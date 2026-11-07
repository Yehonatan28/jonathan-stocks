"""Demo state for previewing the dashboard without any API key.

    PYTHONPATH=src python -m newsroom.tools.demo      -> dashboard/public/data.json (marked "demo")

Every number here is invented for layout review only, and the page shows a "demo data" banner.
"""
from __future__ import annotations

import json
import math
import random
import tempfile
from datetime import datetime, timedelta

from .. import scheduler as sch
from ..config import Config
from ..context import Context
from ..models import Story
from ..site import build
from ..storage.state import State

MOVES = {  # symbol: (change %, daily stdev %)
    "SPY": (-0.82, 1.0), "QQQ": (-1.35, 1.3), "DIA": (-0.21, 0.9), "IWM": (0.34, 1.4),
    "XLK": (-1.9, 1.4), "XLF": (0.6, 1.1), "XLE": (2.4, 1.5), "XLV": (0.3, 0.9), "XLY": (-0.7, 1.3),
    "XLP": (0.4, 0.7), "XLI": (-0.2, 1.0), "XLU": (0.8, 1.0), "XLB": (0.1, 1.2), "XLRE": (0.5, 1.2),
    "XLC": (-1.1, 1.3), "USO": (3.6, 2.0), "BNO": (3.2, 1.9), "GLD": (0.4, 0.9), "UUP": (0.3, 0.4),
    "IBIT": (1.8, 3.0), "MSTR": (4.9, 5.5), "TTWO": (-0.4, 1.8), "WMT": (1.9, 0.9), "GOOG": (-1.6, 1.7),
    "NVDA": (-5.8, 2.6), "AAPL": (-1.4, 1.4), "AMZN": (-0.9, 1.8), "MSFT": (-1.7, 1.3), "TSLA": (2.2, 3.4),
    "SPCX": (6.1, 3.9), "MAGS": (-2.1, 1.5), "META": (-1.2, 2.0), "AVGO": (-3.1, 2.6), "JPM": (0.9, 1.2),
    "BRK.B": (0.2, 0.8), "GOOGL": (-1.6, 1.7), "EIS": (-0.6, 1.3), "TEVA": (1.1, 2.2), "CHKP": (-0.3, 1.5),
}
PRICES = {"SPY": 682.4, "QQQ": 611.2, "DIA": 471.9, "IWM": 247.1, "NVDA": 186.3, "AAPL": 268.0, "MSFT": 497.2,
          "GOOG": 281.6, "AMZN": 244.5, "TSLA": 438.0, "WMT": 104.2, "MSTR": 268.9, "IBIT": 58.1,
          "TTWO": 247.7, "SPCX": 171.4, "XLE": 92.6, "MAGS": 66.2}

STORIES = [
    ("Nvidia slides as hyperscalers signal slower AI capex growth", ["NVDA", "MSFT", "GOOG"], -1, 6, 13.2),
    ("Oil jumps after OPEC+ agrees to extend output cuts into 2027", ["XLE"], 1, 5, 9.4),
    ("Treasury yields climb ahead of Thursday's CPI report", [], -1, 4, 11.0),
    ("Walmart lifts holiday outlook on strong grocery demand", ["WMT"], 1, 4, 14.1),
    ("SpaceX shares surge after Starship completes orbital refuelling test", ["SPCX"], 1, 3, 15.6),
    ("Bitcoin tops $108,000 as ETF inflows accelerate", ["IBIT", "MSTR"], 1, 4, 10.3),
    ("Fed's Waller says policy is well positioned for patience", [], 0, 3, 16.4),
    ("Take-Two confirms GTA VI marketing push begins next month", ["TTWO"], 0, 2, 12.5),
    ("Bank stocks rally on lighter capital rules proposal", [], 1, 3, 15.0),
    ("Tesla gains after record Model Y deliveries in China", ["TSLA"], 1, 2, 17.2),
]
SOURCES = ["CNBC", "MarketWatch", "Yahoo Finance", "Investing.com", "Nasdaq", "Finnhub"]


def make_state(root, now: datetime) -> State:
    rnd = random.Random(7)
    st = State(root)
    cfg = Config.load()
    ny_day = now.astimezone(sch.NY).date()
    t_open = datetime.combine(ny_day, sch.OPEN_ET, sch.NY)
    quotes = {}
    for s, (chg, sd) in MOVES.items():
        price = PRICES.get(s, 50 + rnd.random() * 200)
        quotes[s] = {"price": price, "change_pct": chg, "prev_close": round(price / (1 + chg / 100), 2),
                     "time": int(now.timestamp()) - 120, "source": "Finnhub", "sigma": round(chg / sd, 2), "stdev": sd}
    quotes["BTC"] = {"price": 108420.0, "change_pct": 3.4, "prev_close": 104860.0, "time": int(now.timestamp()),
                     "source": "CoinGecko", "sigma": None, "stdev": None}
    quotes["^VIX"] = {"price": 19.4, "change_pct": 8.1, "prev_close": 17.95, "time": int(now.timestamp()),
                      "source": "Yahoo (גיבוי)", "sigma": None, "stdev": None}
    quotes["^TNX"] = {"price": 4.27, "change_pct": 1.9, "prev_close": 4.19, "time": int(now.timestamp()),
                      "source": "Yahoo (גיבוי)", "sigma": None, "stdev": None}
    monday = ny_day - timedelta(days=ny_day.weekday())
    macro = [{"label": "מדד המחירים לצרכן (CPI)", "date": (monday + timedelta(days=3)).isoformat(), "time_et": "08:30", "tier": 1},
             {"label": "מכירות קמעונאיות", "date": (monday + timedelta(days=4)).isoformat(), "time_et": "08:30", "tier": 2},
             {"label": "משרות פנויות (JOLTS)", "date": (monday + timedelta(days=1)).isoformat(), "time_et": "10:00", "tier": 2}]
    earnings = [{"symbol": "NVDA", "date": (monday + timedelta(days=2)).isoformat(), "hour": "amc", "eps_estimate": 1.05,
                 "eps_actual": None, "revenue_estimate": None, "revenue_actual": None},
                {"symbol": "WMT", "date": (monday + timedelta(days=4)).isoformat(), "hour": "bmo", "eps_estimate": 0.6,
                 "eps_actual": None, "revenue_estimate": None, "revenue_actual": None},
                {"symbol": "CRM", "date": (monday + timedelta(days=1)).isoformat(), "hour": "amc", "eps_estimate": 2.4,
                 "eps_actual": None, "revenue_estimate": None, "revenue_actual": None}]
    st.set_cache("market", {"quotes": quotes, "updated": int(now.timestamp()),
                            "fred": {"DGS10": {"date": "2026-11-09", "value": 4.19, "prev": 4.14, "change": 0.05},
                                     "VIXCLS": {"date": "2026-11-09", "value": 17.95, "prev": 16.8, "change": 1.15}},
                            "macro_upcoming": macro, "earnings": earnings})
    # intraday: a random walk ending at today's change, every 15 minutes since the open
    series = {}
    n = max(2, int((min(now, t_open + timedelta(hours=6.5)) - t_open).total_seconds() // 900) + 1)
    for s in cfg.watchlist + cfg.index_symbols:
        chg, sd = MOVES.get(s, (0, 1))
        p0 = quotes[s]["prev_close"]
        pts, walk = [], 0.0
        for i in range(n):
            walk += rnd.gauss(0, sd / 6)
            frac = i / (n - 1)
            c = chg * frac + walk * math.sin(math.pi * frac)
            pts.append([int((t_open + timedelta(minutes=15 * i)).timestamp()), round(p0 * (1 + c / 100), 2), round(c, 2)])
        series[s] = pts
    st.set_cache(f"intraday-{ny_day.isoformat()}", series)
    # stories, spread across the Israeli day
    il_day = now.astimezone(sch.IL).date()
    rows = []
    for i, (title, tickers, sent, n_src, hour) in enumerate(STORIES):
        base = datetime.combine(il_day, datetime.min.time(), sch.IL) + timedelta(hours=hour)
        for j in range(n_src):
            s = Story(title if j == 0 else title.replace(" as ", " while ").replace(" after ", " following "),
                      f"https://example.com/demo/{i}/{j}", SOURCES[j % len(SOURCES)],
                      int((base + timedelta(minutes=9 * j)).timestamp()), tickers=tickers, quality=3 if j < 2 else 2)
            rows.append(s.archive_row())
    st.archive(il_day, rows)
    st.set_cache("alerts_log", [
        {"ts": int(now.timestamp()) - 5400, "kind": "move", "score": 8.6, "urgent": False, "symbol": "NVDA",
         "headline": "🟠 NVDA  ▼ −5.80%   (תנועה חריגה: 2.2 סטיות תקן)",
         "what": "המניה ירדה אחרי שענקיות הענן רמזו על האטה בהשקעות ב-AI.",
         "why": "NVDA היא גם חלק מ-MAGS, אז הירידה פוגעת בתיק פעמיים.", "url": "https://example.com/demo/0/0"},
        {"ts": int(now.timestamp()) - 3000, "kind": "market", "score": 7.5, "urgent": False, "symbol": "USO",
         "headline": "🟠 נפט WTI  ▲ +3.60%", "what": "OPEC+ האריכה את קיצוצי ההפקה.",
         "why": "משפיע על: XLE", "url": "https://example.com/demo/1/0"},
    ])
    st.set_cache("edition-morning", {"date": il_day.isoformat(), "sent_at": int(now.timestamp()) - 36000, "html":
        "☀️ <b>מהדורת בוקר</b> · נתוני הדגמה\n📌 <b>הטכנולוגיה הובילה ירידה, האנרגיה הציעה מקלט</b>\n\n"
        "⚡ <b>שלושה דברים שחייבים לדעת</b>\n• ענקיות הענן רומזות על האטה בהשקעות AI.\n"
        "• OPEC+ מאריכה קיצוצים, הנפט מזנק.\n• מדד המחירים לצרכן יתפרסם ביום חמישי."})
    return st


def run() -> int:
    now = datetime.now(sch.UTC)
    ny = now.astimezone(sch.NY)
    if not sch.is_trading_day(ny.date()) or ny.time() < sch.OPEN_ET:     # show a mid-session picture
        d = sch.previous_trading_day(ny.date() + timedelta(days=1)) if sch.is_trading_day(ny.date()) \
            else sch.previous_trading_day(ny.date())
        now = datetime.combine(d, datetime.strptime("13:40", "%H:%M").time(), sch.NY).astimezone(sch.UTC)
    with tempfile.TemporaryDirectory() as tmp:
        st = make_state(tmp, now)
        ctx = Context(Config.load(), st, now=now)
        data = build.build_data(ctx)
    data["demo"] = True
    build.LOCAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    build.LOCAL_OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"demo data -> {build.LOCAL_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
