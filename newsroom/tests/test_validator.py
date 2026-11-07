from newsroom.llm.validator import allowed_numbers, invalid_numbers, numbers_in, validate_fields

FACTS = {
    "indices": [{"name": "S&P 500", "change_pct": -1.23}, {"name": "נאסד\"ק 100", "change_pct": 0.81}],
    "btc": {"price_usd": 104250, "change_pct": 3.07},
    "y10": {"value": 4.21, "change_bp": 5},
    "headline": "Nvidia falls 6.2% after guidance; H100 supply update",
    "filing": "8-K",
}
ALLOWED = allowed_numbers(FACTS)


def test_extracts_numbers_with_hebrew_prefixes():
    assert [str(n) for n in numbers_in("ירד ב-1.23% ועלה ב3%")] == ["1.23", "3"]
    assert [str(n) for n in numbers_in("ביטקוין ב-$104,250")] == ["104250"]


def test_latin_glued_tokens_are_not_numbers():
    assert numbers_in("Q3 ו-H100") == []


def test_exact_and_rounded_numbers_pass():
    assert invalid_numbers("ה-S&P 500 ירד 1.23%", ALLOWED) == []
    assert invalid_numbers("ה-S&P 500 ירד 1.2%", ALLOWED) == []          # rounded
    assert invalid_numbers("עלייה של 5 נ\"ב לתשואה של 4.21%", ALLOWED) == []
    assert invalid_numbers("ביטקוין עלה 3.1% ל-104,250 דולר", ALLOWED) == []
    assert invalid_numbers("נאסד\"ק 100 עלה", ALLOWED) == []
    assert invalid_numbers("הגשת 8-K", ALLOWED) == []


def test_invented_numbers_fail():
    assert invalid_numbers("המניה ירדה 7.5%", ALLOWED) == ["7.5"]
    assert invalid_numbers("יעד מחיר 150 דולר", ALLOWED) == ["150"]
    assert invalid_numbers("ירד ב-3%", ALLOWED) == ["3"]
    assert invalid_numbers("עלה 1.3%", ALLOWED) == ["1.3"]                 # 1.23 does not round to 1.3


def test_numbers_inside_headlines_are_allowed():
    assert invalid_numbers("אנבידיה ירדה 6.2%", ALLOWED) == []


def test_validate_fields_removes_only_bad_sentences():
    out = {
        "headline": "השוק ירד 1.2%",
        "three_things": [{"story_id": "s1", "text": "ירידה של 1.23%"},
                         {"story_id": "s2", "text": "זינוק של 12%"}],
        "my_stocks": {"NVDA": "ירדה 6.2%", "AAPL": "עלתה 4%"},
    }
    clean, problems = validate_fields(out, ALLOWED)
    assert clean["headline"] == "השוק ירד 1.2%"
    assert clean["three_things"][1]["text"] is None
    assert clean["my_stocks"] == {"NVDA": "ירדה 6.2%", "AAPL": None}
    assert len(problems) == 2


def test_story_ids_are_not_checked_as_numbers():
    clean, problems = validate_fields({"three_things": [{"story_id": "s12", "text": "בלי מספרים"}]}, ALLOWED)
    assert problems == []
