"""Headline tone: lists, negation, Hebrew prefixes, neutral when nothing matches."""
import tone as T


def test_english():
    assert T.label('Nvidia shares surge after earnings beat')['tone'] == 'positive'
    assert T.label('Tesla stock plunges as deliveries miss estimates')['tone'] == 'negative'
    assert T.label('Fed holds rates steady')['tone'] == 'neutral'
    r = T.label('Apple shares rise despite tariff concerns')
    assert r['tone'] == 'negative' and set(r['words']) == {'concerns', 'rise', 'tariff'}


def test_negation_flips():
    assert T.label('Company did not beat expectations')['tone'] == 'negative'
    assert T.label('No recession in sight, economists say')['tone'] == 'positive'


def test_hebrew_with_prefixes():
    assert T.label('זינוק במניית טבע לאחר האישור')['tone'] == 'positive'
    assert T.label('הבורסה בתל אביב: ירידה חדה ופיטורים בהייטק')['tone'] == 'negative'
    assert T.label('לא ירידה אלא יציבות')['tone'] == 'positive'


def test_score_range():
    r = T.label('profit growth beat')
    assert r['score'] == 1.0 and T.label('')['score'] == 0.0
