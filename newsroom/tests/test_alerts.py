"""Alerts: importance score, detectors, anti-noise."""
import time
from datetime import date, datetime

import pytest

from newsroom import scheduler as sch
from newsroom.alerts import detect
from newsroom.alerts.antinoise import AntiNoise, take_queue
from newsroom.alerts.format import combine
from newsroom.alerts.macro import compute
from newsroom.alerts.models import Alert
from newsroom.config import Config
from newsroom.models import EarningsEvent, Filing, Quote, Story
from newsroom.processing import cluster as cl
from newsroom.processing.scoring import score_all, score_cluster, sentiment
from newsroom.processing.volatility import VolProfile
from newsroom.snapshot import Snapshot
from newsroom.storage.state import State

NOW = datetime(2026, 11, 10, 16, 0, tzinfo=sch.UTC).timestamp()      # 11:00 NY, 18:00 Israel


def cfg():
    c = Config.load()
    c.watchlist = ["NVDA", "WMT", "MSTR", "MAGS", "AAPL", "XLE", "IBIT"]
    return c


def snap(**moves):
    s = Snapshot(date(2026, 11, 10), date(2026, 11, 10), date(2026, 11, 9))
    for sym, (chg, sd) in moves.items():
        s.quotes[sym] = Quote(sym, 100.0, chg, 100.0, int(NOW) - 60, "Finnhub")
        s.profiles[sym] = VolProfile(sd, 60, False)
        s.sigmas[sym] = round(chg / sd, 2)
    return s


def st(title, source, url, ts=NOW - 600, tickers=(), kind="news", q=2):
    return Story(title, url, source, int(ts), kind=kind, tickers=list(tickers), quality=q)


# ---------------------------------------------------------------- scoring ---

def test_sentiment():
    assert sentiment("Nvidia beats estimates, shares surge") == 1
    assert sentiment("Walmart misses, stock falls") == -1
    assert sentiment("Fed meeting minutes released") == 0


def test_score_grows_with_sources_relevance_and_reaction():
    one = cl.Cluster([st("Random company opens office", "CNBC", "u1")])
    many = cl.Cluster([st("Nvidia guidance disappoints", s, f"u{i}", tickers=["NVDA"])
                       for i, s in enumerate(["CNBC", "MarketWatch", "Yahoo Finance", "Investing.com"])])
    kw = ["guidance", "fed"]
    s1 = score_cluster(one, watchlist={"NVDA"}, megacaps={"NVDA"}, sigmas={}, keywords=kw)
    s2 = score_cluster(many, watchlist={"NVDA"}, megacaps={"NVDA"}, sigmas={"NVDA": -2.5}, keywords=kw)
    assert s1.score <= 2
    assert s2.score >= 9
    assert any("NVDA" in r for r in s2.reasons)


def test_score_is_clamped_and_llm_only_nudges():
    c = cl.Cluster([st("Fed cuts rates; FOMC guidance", s, f"u{i}", kind="fed", tickers=["NVDA"])
                    for i, s in enumerate("ABCDEFG")])
    s = score_cluster(c, watchlist={"NVDA"}, megacaps=set(), sigmas={"NVDA": 9}, keywords=["fed"], llm_rating=1)
    assert s.score <= 10
    assert s.score >= 7          # a low model rating cannot sink a 10 below 7.3


# -------------------------------------------------------------- detectors ---

def test_volatility_adjusted_moves():
    c = cfg()
    s = snap(WMT=(2.5, 1.0), MSTR=(5.0, 4.5), NVDA=(-9.0, 2.5))
    found = {a.symbol: a for a in detect.watch_moves(s, c, NOW)}
    assert "WMT" in found                 # 2.5σ for a calm stock
    assert "MSTR" not in found            # 5% is a normal day for MSTR
    assert found["NVDA"].score >= 9       # 3.6σ is urgent
    assert "סטיות תקן" in found["NVDA"].headline and "▼" in found["NVDA"].headline


def test_stale_quotes_do_not_alert():
    c = cfg()
    s = snap(WMT=(3.0, 1.0))
    s.quotes["WMT"].time = int(NOW) - 86400
    assert detect.watch_moves(s, c, NOW) == []


def test_market_wide_thresholds():
    c = cfg()
    s = snap(SPY=(-1.8, 1.0), QQQ=(-1.5, 1.2), USO=(4.5, 2.0))
    s.btc = Quote("BTC", 90000, -6.0, 95000, int(NOW), "CoinGecko")
    s.yahoo["^TNX"] = Quote("^TNX", 4.32, 2.6, 4.20, int(NOW), "Yahoo")
    keys = {a.key.split(":")[1] for a in detect.market_moves(s, c, NOW)}
    assert keys == {"SPY", "BTC", "USO", "^TNX"}       # QQQ -1.5% is below its 2% threshold
    oil = next(a for a in detect.market_moves(s, c, NOW) if a.symbol == "USO")
    assert "XLE" in oil.tickers                          # oil -> my XLE


def test_earnings_surprise_is_computed_not_written():
    c = cfg()
    s = snap(NVDA=(4.0, 2.5))
    s.earnings_reported = [EarningsEvent("NVDA", "2026-11-10", "bmo", 1.00, 1.15, None, None)]
    a = detect.earnings(s, c)[0]
    assert a.facts["surprise_pct"] == 15.0
    assert a.score == 9.0 and "+15.0%" in a.what


def test_filings_and_fomc():
    c = cfg()
    s = snap()
    s.filings = [Filing("NVDA", "8-K", "2026-11-10T13:00:00+00:00", "https://sec/x", "2.02,9.01")]
    s.fed = [st("Federal Reserve issues FOMC statement", "Federal Reserve", "https://fed/1", kind="fed")]
    assert detect.filings(s, c)[0].score == 8.0
    assert detect.fomc(s)[0].score >= 9


def test_hot_story_unrelated_to_watchlist():
    c = cfg()
    s = snap()
    stories = [st("Boeing halts 737 deliveries after FAA order", src, f"b{i}")
               for i, src in enumerate(["CNBC", "MarketWatch", "Yahoo Finance", "Investing.com"])]
    s.clusters = cl.cluster(stories)
    scored = score_all(s.clusters, c, {})
    alerts = detect.stories(scored, s, c, NOW)
    assert alerts and alerts[0].score >= 7.5 and "סיפור חם" in alerts[0].headline


def test_macro_compute():
    obs = [{"value": "320.0"}, {"value": "319.04"}, {"value": "318.40"}]
    assert compute("mom", obs) == (0.3, 0.2)
    assert compute("diff", [{"value": "159500"}, {"value": "159300"}, {"value": "159150"}]) == (200.0, 150.0)
    assert compute("level", [{"value": "4.2"}, {"value": "4.1"}]) == (4.2, 4.1)


# -------------------------------------------------------------- anti-noise ---

SETTINGS = {"alerts": {"threshold": 7, "urgent": 9, "cooldown_minutes": 120, "daily_cap": 2},
            "quiet_hours": {"start": "23:30", "end": "06:30"}}


def A(key, score, tickers=("NVDA",), kind="move", level=2, tokens=()):
    return Alert(key=key, kind=kind, score=score, headline=key, what="w", why="y", symbol=tickers[0] if tickers else None,
                 tickers=list(tickers), level=level, tokens=list(tokens))


def test_dedupe_and_threshold(tmp_path):
    s = State(tmp_path)
    an = AntiNoise(s, SETTINGS, NOW)
    send, q = an.decide([A("k1", 8), A("low", 5, tickers=("WMT",))])
    assert [a.key for a in send] == ["k1"] and q == []
    an.commit(send, q)
    an2 = AntiNoise(s, SETTINGS, NOW + 60)
    assert an2.decide([A("k1", 8)]) == ([], [])


def test_cooldown_and_escalation(tmp_path):
    s = State(tmp_path)
    an = AntiNoise(s, SETTINGS, NOW)
    send, q = an.decide([A("m2", 7.5, level=2)])
    an.commit(send, q)
    an = AntiNoise(s, SETTINGS, NOW + 1800)
    send, q = an.decide([A("story-nvda", 7.2, kind="story", level=0)])
    assert send == [] and [a.key for a in q] == ["story-nvda"]          # cooldown -> queued
    send, q = an.decide([A("m3", 8.0, level=3)])
    assert [a.key for a in send] == ["m3"]                               # escalation breaks it
    send, q = an.decide([A("earn", 8.0, kind="earnings", level=1)])
    assert [a.key for a in send] == ["earn"]                             # new event type breaks it


def test_daily_cap_spares_urgent(tmp_path):
    s = State(tmp_path)
    an = AntiNoise(s, SETTINGS, NOW)
    alerts = [A(f"k{i}", 7.5, tickers=(f"T{i}",)) for i in range(4)] + [A("u", 9.5, tickers=("U",))]
    send, q = an.decide(alerts)
    assert {a.key for a in send} == {"u", "k0", "k1"}
    assert len(q) == 2
    an.commit(send, q)
    items = take_queue(s)
    assert len(items) == 2 and take_queue(s) == []


def test_quiet_hours_only_urgent_and_silent(tmp_path):
    s = State(tmp_path)
    night = datetime(2026, 11, 10, 1, 0, tzinfo=sch.IL).timestamp()
    an = AntiNoise(s, SETTINGS, night)
    send, q = an.decide([A("n", 8, tickers=("A",)), A("u", 9.6, tickers=("B",))])
    assert [a.key for a in send] == ["u"] and send[0].silent
    assert [a.key for a in q] == ["n"]


def test_pause_queues_everything(tmp_path):
    s = State(tmp_path)
    s.set("paused_until", NOW + 3600)
    send, q = AntiNoise(s, SETTINGS, NOW).decide([A("u", 9.6)])
    assert send == [] and len(q) == 1


def test_same_story_new_headline_is_not_resent(tmp_path):
    s = State(tmp_path)
    an = AntiNoise(s, SETTINGS, NOW)
    t1 = cl.tokens("Nvidia shares fall after weak data center guidance")
    send, q = an.decide([A("s1", 8, tickers=(), kind="story", tokens=t1)])
    an.commit(send, q)
    t2 = cl.tokens("Nvidia stock falls on weak data center guidance")
    an = AntiNoise(s, SETTINGS, NOW + 7200)
    assert an.decide([A("s2", 8, tickers=(), kind="story", tokens=t2)]) == ([], [])


def test_combined_message():
    a, b = A("a", 8), A("b", 9.5, tickers=("WMT",))
    b.urgent = True
    msg = combine([a, b], "https://dash")
    assert msg.startswith("🔔 <b>2 עדכונים</b> · 1 דחופים")
    assert "מה קרה" in msg and "https://dash/#t=WMT" in msg
