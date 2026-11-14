"""🎧 The spoken morning edition: a Hebrew script built from the same facts, read by edge-tts.

The script is written for the ear, not the eye: no emoji, no links, no English headlines,
arrows and signs become words ("עלייה של 1.2 אחוז"), and tickers become company names.
It uses only the validated sentences of the written edition plus numbers from the facts,
so the iron rule (numbers from the APIs only) holds here too.

edge-tts uses Microsoft's online voices without an API key. It is unofficial and may stop
working one day; when it fails, the written edition is unaffected.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

from . import scheduler as sch

log = logging.getLogger(__name__)

SAY_NAMES = {
    "NVDA": "אנבידיה", "AAPL": "אפל", "MSFT": "מייקרוסופט", "GOOG": "גוגל", "GOOGL": "גוגל", "AMZN": "אמזון",
    "TSLA": "טסלה", "WMT": "וולמארט", "MSTR": "סטרטג'י", "IBIT": "תעודת הביטקוין של בלאקרוק",
    "TTWO": "טייק טו", "SPCX": "ספייס אקס", "XLE": "תעודת האנרגיה", "MAGS": "תעודת שבע המופלאות",
    "META": "מטא", "AVGO": "ברודקום", "SPY": "אס אנד פי", "QQQ": "נאסדק", "DIA": "דאו ג'ונס", "IWM": "ראסל",
    "BTC": "ביטקוין", "EIS": "תעודת הסל של ישראל",
}
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def say_pct(x: float | None) -> str:
    if x is None:
        return "אין נתון"
    v = round(abs(x), 1)
    if v == 0:
        return "ללא שינוי"
    return f"{'עלייה' if x > 0 else 'ירידה'} של {v:g} אחוז"


def speakable(text: str | None) -> str:
    """Turn an edition sentence into something a voice reads naturally."""
    if not text:
        return ""
    t = _EMOJI.sub("", text)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"▲\s*\+?\s*([\d.]+)\s*%", r"עלייה של \1 אחוז", t)
    t = re.sub(r"▼\s*[−-]?\s*([\d.]+)\s*%", r"ירידה של \1 אחוז", t)
    t = t.replace("■", "")
    t = re.sub(r"\$\s?([\d,]+(?:\.\d+)?)", r"\1 דולר", t)
    t = re.sub(r"([\d.]+)\s*σ", r"\1 סטיות תקן", t)
    t = t.replace("σ", " סטיות תקן ").replace('נ"ב', "נקודות בסיס").replace("%", " אחוז")
    t = re.sub(r"\b10Y\b", "תשואת האג\"ח לעשר שנים", t)
    t = t.replace("S&P 500", "אס אנד פי").replace("S&P", "אס אנד פי").replace('נאסד"ק', "נאסדק")
    t = re.sub(r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])", lambda m: SAY_NAMES.get(m.group(1), m.group(1)), t)
    t = t.replace("·", ",").replace("•", "").replace("&amp;", "ו")
    return re.sub(r"\s+", " ", t).strip()


def script(facts: dict, text: dict | None, today_il) -> str:
    """The full spoken morning edition, from the validated facts and sentences."""
    text = text or {}
    parts: list[str] = [f"בוקר טוב. זו מהדורת הבוקר של {sch.heb_date(today_il)}."]
    if text.get("headline"):
        parts.append(speakable(text["headline"]) + ".")
    things = [x.get("text") for x in text.get("three_things") or [] if isinstance(x, dict) and x.get("text")]
    if things:
        parts.append("שלושה דברים שחייבים לדעת.")
        parts += [f"{['ראשון', 'שני', 'שלישי'][i]}: {speakable(t)}" for i, t in enumerate(things[:3])]
    idx = facts.get("indices_last_session") or []
    if idx:
        if facts.get("session_note"):
            parts.append(speakable(facts["session_note"]))
        parts.append("בוול סטריט: " + ", ".join(f"{speakable(i['name'])}, {say_pct(i['change_pct'])}" for i in idx[:3]) + ".")
        sect = facts.get("sectors_last_session") or []
        if len(sect) >= 2:
            parts.append(f"הסקטור המוביל: {sect[0]['name']}, {say_pct(sect[0]['change_pct'])}. "
                         f"המפגר: {sect[-1]['name']}, {say_pct(sect[-1]['change_pct'])}.")
    if text.get("what_moved"):
        parts.append(speakable(text["what_moved"]))
    stocks = facts.get("my_stocks") or []
    if stocks:
        why = text.get("my_stocks") or {}
        parts.append("המניות שלך.")
        for r in stocks:
            line = f"{SAY_NAMES.get(r['ticker'], r['ticker'])}: {say_pct(r.get('change_pct'))}."
            if why.get(r["ticker"]):
                line += " " + speakable(why[r["ticker"]])
            parts.append(line)
    hot = [x.get("text") for x in text.get("hot_stories") or [] if isinstance(x, dict) and x.get("text")]
    if hot:
        parts.append("ומה עוד מדברים עליו. " + " ".join(speakable(h) for h in hot[:3]))
    btc = (facts.get("overnight") or {}).get("ביטקוין")
    if btc:
        parts.append(f"בלילה, ביטקוין: {say_pct(btc.get('change_24h_pct'))} ביממה האחרונה.")
    today = facts.get("today") or {}
    if today.get("open_israel_time"):
        parts.append(f"המסחר בניו יורק ייפתח היום ב-{today['open_israel_time']} שעון ישראל"
                     + (", ויהיה יום מקוצר." if today.get("early_close") else "."))
    elif today.get("us_market"):
        parts.append(f"הבורסה בניו יורק {speakable(today['us_market'])} היום.")
    for m in today.get("macro") or []:
        parts.append(f"ב-{m['time_israel']}: {speakable(m['label'])}.")
    if today.get("fomc_decision"):
        parts.append("היום גם החלטת הריבית של הפד.")
    earn = [e["symbol"] for e in today.get("earnings") or []]
    if earn:
        parts.append("דוחות היום: " + ", ".join(SAY_NAMES.get(s, s) for s in earn[:6]) + ".")
    if text.get("israel_line"):
        parts.append("ובתל אביב: " + speakable(text["israel_line"]))
    concept = text.get("concept") or {}
    if concept.get("term") and concept.get("explain"):
        parts.append(f"והמושג של היום: {speakable(concept['term'])}. {speakable(concept['explain'])}")
    parts.append("זה הכול להבוקר. מידע בלבד, לא המלצה. יום טוב.")
    return "\n".join(p for p in parts if p)


def _ensure_edge_tts() -> None:
    """edge-tts is installed only in the run that needs it (once a day), not in every heartbeat,
    which keeps the 1,300+ monthly runs inside GitHub's free minutes."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        import subprocess
        import sys
        req = Path(__file__).resolve().parents[2] / "requirements-audio.txt"
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req)], check=True, timeout=120)


async def _synth(text: str, voice: str, rate: str, out: Path) -> None:
    import edge_tts
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    await edge_tts.Communicate(text, voice, rate=rate, proxy=proxy).save(str(out))


def synthesize(text: str, voice: str = "he-IL-AvriNeural", rate: str = "+0%") -> Path:
    _ensure_edge_tts()
    out = Path(tempfile.mkdtemp(prefix="newsroom-audio-")) / "morning.mp3"
    asyncio.run(asyncio.wait_for(_synth(text, voice, rate, out), timeout=60))
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("edge-tts produced no audio")
    return out


def send_morning_audio(ctx, facts: dict, text: dict | None, today_il) -> bool:
    """Best effort: any failure is recorded as a failed source, never raised."""
    cfg = ctx.cfg.s("audio", default={}) or {}
    if not cfg.get("enabled", False):
        return False
    try:
        spoken = script(facts, text, today_il)[: int(cfg.get("max_chars", 3500))]
        path = synthesize(spoken, cfg.get("voice", "he-IL-AvriNeural"), cfg.get("rate", "+0%"))
        ctx.telegram.send_audio(path, title=f"מהדורת הבוקר · {sch.heb_date(today_il)}", performer="חדר החדשות",
                                silent=True)
        return True
    except Exception as exc:  # noqa: BLE001 - the voice is a bonus; the written edition already went out
        ctx.fail("קול (edge-tts)", exc)
        log.warning("audio edition failed: %s", exc)
        return False
