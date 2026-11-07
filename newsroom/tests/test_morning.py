"""The morning edition end to end, offline: fake data in, Telegram HTML out."""
import re
from datetime import date, datetime
from html.parser import HTMLParser

from newsroom import scheduler as sch
from newsroom.config import Config
from newsroom.editions import morning as m
from newsroom.llm.validator import allowed_numbers, validate_fields
from newsroom.models import Filing, Quote, Story
from newsroom.processing import cluster as cl
from newsroom.processing.volatility import VolProfile


def cfg():
    c = Config.load()
    c.watchlist = ["NVDA", "AAPL", "MSFT", "GOOG", "WMT", "MAGS", "IBIT"]
    c.settings["dashboard_url"] = ""
    return c


def data():
    d = m.MorningData(today_il=date(2026, 11, 10), today_ny=date(2026, 11, 10), session=date(2026, 11, 9))
    moves = {"SPY": -1.23, "QQQ": -1.9, "DIA": -0.4, "IWM": 0.3, "XLK": -2.4, "XLE": 1.1, "XLU": 0.2,
             "NVDA": -6.2, "AAPL": -1.8, "MSFT": -1.5, "GOOG": -2.1, "WMT": 0.1, "MAGS": -2.0, "IBIT": 0.4,
             "EIS": -0.7}
    for s, chg in moves.items():
        d.quotes[s] = Quote(s, 100.0, chg, 100.0, 0, "Finnhub")
        prof = VolProfile(2.5 if s == "NVDA" else 1.0, 60, False)
        d.profiles[s] = prof
        d.sigmas[s] = round(chg / prof.stdev_pct, 2)
    d.btc = Quote("BTC", 104250.0, 3.07, 101000.0, 0, "CoinGecko")
    d.fred = {"DGS10": {"date": "2026-11-09", "value": 4.21, "prev": 4.16, "change": 0.05}}
    d.stories = [
        Story("Nvidia falls after weak data center guidance", "https://x/1", "CNBC", 1000, tickers=["NVDA"]),
        Story("Nvidia stock falls on weak guidance", "https://x/2", "MarketWatch", 999, tickers=["NVDA"]),
        Story("Oil rises as OPEC+ extends output cuts", "https://x/3", "CNBC", 998),
        Story("Oil rises after OPEC+ extends cuts", "https://x/4", "Yahoo Finance", 997),
        Story("Treasury yields climb before inflation report", "https://x/5", "CNBC", 996),
        Story("Fed's Powell says policy is well positioned", "https://x/6", "MarketWatch", 995),
        Story("Walmart expands drone delivery to five states", "https://x/7", "Yahoo Finance", 994),
        Story("Bank stocks rally on deregulation hopes", "https://x/8", "CNBC", 993),
    ]
    d.clusters = cl.cluster(d.stories)
    d.filings = [Filing("NVDA", "8-K", "2026-11-09T21:00:00+00:00", "https://sec/1", "2.02")]
    return d


class _Checker(HTMLParser):
    ALLOWED = {"b", "i", "a", "code", "u", "s", "pre"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED:
            self.bad.append(tag)
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, f"unbalanced </{tag}>"


def assert_valid_telegram_html(text):
    p = _Checker()
    p.feed(text)
    assert not p.bad and not p.stack


def test_fallback_edition_without_model():
    c, d = cfg(), data()
    facts, refs, stocks = m.build_facts(d, c)
    msg = m.render(d, c, facts, refs, stocks, None, "⚙️ מהדורת גיבוי", ["FRED"],
                   datetime(2026, 11, 10, 5, 0, tzinfo=sch.UTC))
    assert_valid_telegram_html(msg)
    for header in ("📌", "⚡", "📊", "💼", "🔥", "🌙", "📅", "🇮🇱", "📚"):
        assert header in msg
    assert "▼ −1.23%" in msg                 # arrow + sign, not colour alone
    assert "NVDA" in msg and "(2.5σ)" in msg
    assert "WMT" not in msg.split("💼")[1].split("🔥")[0]     # no news, no move -> not listed
    assert "ריכוזיות" in msg                 # AAPL/MSFT/GOOG fell together and sit inside MAGS
    assert "⚠️ מקורות שלא ענו: FRED" in msg
    assert "16:30" in msg                     # NY open in Israel time on 10.11
    assert "8-K" in msg
    hot = msg.split("🔥")[1].split("🌙")[0]
    things = msg.split("⚡")[1].split("📊")[0]
    assert not ({l for l in hot.splitlines() if "href" in l} & {l for l in things.splitlines() if "href" in l})
    assert "ועוד מקור" in msg or "ועוד" not in msg


def test_numbers_in_facts_cover_rendered_numbers():
    """The model sees the same numbers that the template prints."""
    c, d = cfg(), data()
    facts, _, _ = m.build_facts(d, c)
    allowed = allowed_numbers(facts)
    _, problems = validate_fields({"x": "S&P 500 ירד 1.23% ו-10Y עלה 5 נ\"ב ל-4.21%. ביטקוין 104,250"}, allowed)
    assert problems == []


def test_model_text_is_used_and_escaped():
    c, d = cfg(), data()
    facts, refs, stocks = m.build_facts(d, c)
    text = {
        "headline": "הטכנולוגיה הובילה ירידה <חדה>",
        "three_things": [{"story_id": "s1", "text": "אנבידיה ירדה אחרי תחזית חלשה"}],
        "my_stocks": {"NVDA": "התחזית החלשה מכבידה גם על MAGS"},
        "israel_line": "פתיחה חלשה צפויה בתל אביב",
        "concept": {"term": "Guidance", "explain": "תחזית ההנהלה."},
    }
    msg = m.render(d, c, facts, refs, stocks, text, "✍️ נוסח: gemini", [],
                   datetime(2026, 11, 10, 5, 0, tzinfo=sch.UTC))
    assert_valid_telegram_html(msg)
    assert "&lt;חדה&gt;" in msg
    assert "התחזית החלשה מכבידה גם על MAGS" in msg
    assert "פתיחה חלשה צפויה" in msg
    assert re.search(r"⚡.*\n• אנבידיה", msg)


def test_holiday_note():
    c, d = cfg(), data()
    d.today_il = d.today_ny = date(2026, 11, 27)
    d.session = date(2026, 11, 25)
    facts, *_ = m.build_facts(d, c)
    assert "Thanksgiving" in facts["session_note"]
    assert facts["today"]["early_close"] is True
