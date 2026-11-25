"""Machine-labelled tone of a headline, from word lists.

Method (shown to the user as written here):
- A headline (and its summary, when the feed has one) is matched against lists of words that
  usually carry a positive or a negative financial meaning, in the spirit of the
  Loughran-McDonald finance dictionary, with short Hebrew lists for Israeli outlets.
- A word right after a negation ("not", "no", "fails to", "לא") counts the other way.
- Score = (positive - negative) / (positive + negative). Above +0.2 is labelled positive, below -0.2
  negative, otherwise neutral; a headline with no listed word is neutral.
- The words that decided the label are shown with it. This is a crude, transparent signal about
  wording, not an assessment of the news, and it is often wrong on irony or context.
"""
import re

POS = set('''beat beats beating surge surges surged soar soars soared jump jumps jumped rally rallies rallied
gain gains gained rise rises rose climb climbs climbed record upgrade upgrades upgraded outperform outperforms
strong stronger strength growth grow grows grew boost boosts boosted profit profits profitable exceed exceeds
exceeded tops topped raise raises raised optimism optimistic recover recovers recovered recovery rebound rebounds
rebounded win wins won approval approved breakthrough expand expands expanded expansion bullish upbeat robust
dividend buyback higher best accelerate accelerates accelerated improve improves improved improvement'''.split())
NEG = set('''miss misses missed plunge plunges plunged plummet plummets plummeted slump slumps slumped fall falls fell
drop drops dropped decline declines declined sink sinks sank tumble tumbles tumbled slide slides slid lose loses
lost loss losses downgrade downgrades downgraded underperform weak weaker weakness cut cuts cutting layoff layoffs
lawsuit sue sues sued probe investigation fraud default bankruptcy recall recalls warning warns warned fear fears
concern concerns risk risks slowdown recession inflation crash crashes crashed lower worst halt halts halted
fine fined penalty delay delays delayed shortfall bearish volatile volatility selloff sell-off tariff tariffs'''.split())
NEGATORS = {'not', 'no', "n't", 'never', 'without', 'fails', 'failed', 'fail'}
POS_HE = ['זינוק', 'זינק', 'עלייה', 'עלה', 'עלו', 'שיא', 'רווח', 'רווחים', 'צמיחה', 'גדל', 'גדלה', 'התאוששות', 'אישור', 'הכפיל', 'דיבידנד', 'שיפור', 'הצלחה']
NEG_HE = ['צניחה', 'צנח', 'ירידה', 'ירד', 'ירדו', 'הפסד', 'הפסדים', 'נפילה', 'קריסה', 'פיטורים', 'תביעה', 'חקירה', 'אזהרה', 'האטה', 'מיתון', 'אינפלציה', 'משבר', 'קנס', 'עיכוב', 'חשש']
NEG_HE_WORDS = {'לא', 'אין', 'בלי'}


def _he_hits(text, words):
    out = []
    for w in words:
        # a Hebrew word may carry a one- or two-letter prefix (ה, ב, ו, ל, מ, ש, כש...)
        for m in re.finditer(r'(?:^|[\s"\'(])(?:[הבולמשכ]{0,2})' + re.escape(w) + r'(?=$|[\s.,:;!?"\')])', text):
            out.append((m.start(), w))
    return out


def label(title, summary=''):
    text = f'{title} {summary or ""}'
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text.lower())
    pos, neg = [], []
    for i, w in enumerate(words):
        flip = i > 0 and (words[i - 1] in NEGATORS or words[i - 1].endswith("n't"))
        if w in POS:
            (neg if flip else pos).append(w)
        elif w in NEG:
            (pos if flip else neg).append(w)
    for start, w in _he_hits(text, POS_HE):
        before = text[:start].split()[-1:] if start else []
        (neg if before and before[0] in NEG_HE_WORDS else pos).append(w)
    for start, w in _he_hits(text, NEG_HE):
        before = text[:start].split()[-1:] if start else []
        (pos if before and before[0] in NEG_HE_WORDS else neg).append(w)
    n = len(pos) + len(neg)
    score = round((len(pos) - len(neg)) / n, 2) if n else 0.0
    tone = 'positive' if score > 0.2 else 'negative' if score < -0.2 else 'neutral'
    return {'tone': tone, 'score': score, 'words': sorted(set(pos + neg))[:6]}
