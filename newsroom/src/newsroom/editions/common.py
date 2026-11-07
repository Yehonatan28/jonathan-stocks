"""Formatting shared by every edition. Colour never carries meaning alone: arrows and signs too."""
from __future__ import annotations

from datetime import date

UP, DOWN, FLAT = "▲", "▼", "■"


def r2(x: float) -> float:
    return round(float(x), 2)


def pct(x: float | None, digits: int | None = None) -> str:
    if x is None:
        return "אין נתון"
    if digits is None:
        digits = 2 if abs(x) < 10 else 1
    v = round(x, digits)
    if v > 0:
        return f"{UP} +{v:.{digits}f}%"
    if v < 0:
        return f"{DOWN} −{abs(v):.{digits}f}%"
    return f"{FLAT} 0.00%"


def money(x: float) -> str:
    return f"${x:,.0f}" if x >= 1000 else f"${x:,.2f}"


def bp(change: float | None) -> str:
    if change is None:
        return ""
    v = round(change * 100)
    arrow = UP if v > 0 else DOWN if v < 0 else FLAT
    return f"{arrow} {'+' if v > 0 else '−' if v < 0 else ''}{abs(v)} נ\"ב"


def sigma_tag(z: float | None, notable: float = 1.0) -> str:
    if z is None or abs(z) < notable:
        return ""
    return f" ({abs(z):.1f}σ)"


# Fallback "concept of the day" when the model is unavailable: rotates by date.
GLOSSARY = [
    ("סטיית תקן", "מודדת כמה התשואות היומיות של נייר מתפזרות סביב הממוצע. תנועה של 2 סטיות תקן היא חריגה ביחס לנייר עצמו."),
    ("נקודת בסיס (נ\"ב)", "מאית האחוז. עלייה של תשואה מ-4.20% ל-4.30% היא עלייה של 10 נ\"ב."),
    ("VIX", "מדד הפחד: התנודתיות הצפויה ב-S&P 500 ל-30 הימים הבאים, לפי מחירי האופציות."),
    ("Guidance", "התחזית שהחברה נותנת לרבעונים הבאים. לפעמים היא מזיזה את המניה יותר מהתוצאות עצמן."),
    ("תשואת אג\"ח ל-10 שנים", "הריבית שהשוק דורש על חוב ממשלתי ארוך. כשהיא עולה, מניות צמיחה נוטות להיפגע."),
    ("רוחב שוק", "כמה מניות או סקטורים משתתפים בתנועה. עלייה שמגיעה מעט מניות גדולות היא עלייה צרה."),
    ("8-K", "דיווח מיידי ל-SEC על אירוע מהותי: תוצאות, שינוי בהנהלה, עסקה גדולה."),
    ("EPS", "רווח למניה. משווים אותו לציפיות האנליסטים כדי לבדוק אם הייתה הפתעה."),
    ("פרה-מרקט", "מסחר לפני הפתיחה הרשמית (04:00 עד 09:30 בניו יורק). מחזורים נמוכים, ולכן תנודות חדות יותר."),
    ("ריכוזיות", "כשכמה החזקות חשופות לאותו גורם. למשל MAGS יחד עם המניות שהיא מחזיקה."),
    ("מדד הדולר", "שער הדולר מול סל מטבעות. דולר חזק מכביד על רווחי חברות אמריקאיות שמוכרות בחו\"ל."),
    ("CPI", "מדד המחירים לצרכן. נתון גבוה מהצפוי מרחיק הורדות ריבית."),
    ("Core", "אינפלציית ליבה: בלי מזון ואנרגיה, שתנודתיים במיוחד. הפד מסתכל בעיקר עליה."),
    ("FOMC", "הוועדה של הפד שמחליטה על הריבית. מתכנסת שמונה פעמים בשנה."),
]


def concept_of(d: date) -> tuple[str, str]:
    return GLOSSARY[d.toordinal() % len(GLOSSARY)]


HOUR_HE = {"bmo": "לפני הפתיחה", "amc": "אחרי הסגירה", "dmh": "במהלך המסחר"}
