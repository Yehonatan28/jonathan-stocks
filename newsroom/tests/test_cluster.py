from newsroom.models import Story
from newsroom.processing import cluster as cl
from newsroom.processing.links import aliases, mags_overlap, short_name
from newsroom.models import Quote


def st(title, source, url, ts=1000):
    return Story(title=title, url=url, source=source, published=ts)


def test_same_event_from_different_outlets_is_one_story():
    stories = [
        st("Nvidia shares fall after weak data center guidance", "CNBC", "u1", 1003),
        st("Nvidia stock falls on weak data center guidance", "MarketWatch", "u2", 1002),
        st("Nvidia guidance disappoints, shares fall", "Yahoo Finance", "u3", 1001),
        st("Oil jumps as OPEC+ agrees to deeper output cuts", "CNBC", "u4", 1000),
    ]
    cs = cl.cluster(stories)
    assert len(cs) == 2
    top = cl.hot(cs, 1)[0]
    assert top.sources == {"CNBC", "MarketWatch", "Yahoo Finance"}


def test_duplicate_urls_are_dropped():
    stories = [st("A big story", "CNBC", "same"), st("A big story", "CNBC", "same")]
    assert len(cl.cluster(stories)[0].stories) == 1


def test_unrelated_headlines_stay_apart():
    stories = [st("Fed holds rates steady, signals patience", "CNBC", "a"),
               st("Walmart raises full-year outlook", "CNBC", "b")]
    assert len(cl.cluster(stories)) == 2


def test_ticker_tagging():
    stories = [st("Take-Two delays GTA release", "CNBC", "a"),
               st("Strong quarter for Walmart (WMT)", "CNBC", "b"),
               st("Market wrap: stocks rise", "CNBC", "c")]
    cl.tag_tickers(stories, {"TTWO": aliases("TTWO", "Take-Two Interactive Software Inc"),
                             "WMT": aliases("WMT", "Walmart Inc")})
    assert stories[0].tickers == ["TTWO"]
    assert stories[1].tickers == ["WMT"]
    assert stories[2].tickers == []


def test_short_name():
    assert short_name("NVIDIA Corp") == "NVIDIA"
    assert short_name("Walmart Inc.") == "Walmart Inc."  # trailing dot kept, harmless
    assert short_name("Apple Inc") == "Apple"


def q(sym, chg):
    return Quote(sym, 100, chg, 100, 0, "t")


def test_mags_overlap_flags_concentration():
    group = {"etf": "MAGS", "members": ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA"]}
    wl = ["MAGS", "AAPL", "MSFT", "GOOG", "NVDA", "WMT"]
    quotes = {s: q(s, -2) for s in wl}
    sig = {"AAPL": -1.5, "MSFT": -1.2, "GOOG": -2.0, "NVDA": -0.3}
    res = mags_overlap(wl, group, quotes, sig)
    assert res["held_count"] == 4
    assert res["direction"] == "down"
    assert sorted(res["moved_together"]) == ["AAPL", "GOOG", "MSFT"]


def test_mags_overlap_needs_the_etf():
    group = {"etf": "MAGS", "members": ["AAPL"]}
    assert mags_overlap(["AAPL"], group, {}, {}) is None
