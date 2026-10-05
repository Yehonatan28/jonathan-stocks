"""בונה את Pearl Portfolio Tracker — קובץ אקסל / Google Sheets לניהול תיק מניות.

הרצה:  python spreadsheet/build_tracker.py
פלט:   spreadsheet/Pearl_Portfolio_Tracker.xlsx

המחירים: בכל עמודת "מחיר" יש נוסחה היברידית
    =IFERROR(GOOGLEFINANCE(טיקר), מחיר ידני)
ב-Google Sheets המחיר מתעדכן לבד; באקסל נלקח המחיר הידני.
"""
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

OUT = Path(__file__).with_name("Pearl_Portfolio_Tracker.xlsx")

FONT = "Arial"
NAVY = "0F1B2D"
GOLD = "C9A227"
INPUT_FILL = PatternFill("solid", fgColor="FFF6D5")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
SUB_FILL = PatternFill("solid", fgColor="E8EDF5")
KPI_FILL = PatternFill("solid", fgColor="F4F6FA")
THIN = Side(style="thin", color="D0D7E2")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

USD = '$#,##0.00;[Red]-$#,##0.00;"-"'
USD0 = '$#,##0;[Red]-$#,##0;"-"'
PCT = '0.0%;[Red]-0.0%;"-"'
NUM = '#,##0.##;[Red]-#,##0.##;"-"'
RMULT = '0.0"R";[Red]-0.0"R";"-"'
DATE = "dd/mm/yyyy"

TX_FIRST, TX_LAST = 5, 1004          # 1,000 שורות עסקאות
H_FIRST, H_LAST = 5, 54              # 50 פוזיציות
W_FIRST, W_LAST = 5, 44              # 40 מניות במעקב

TYPES = ["קנייה", "מכירה", "דיבידנד", "הפקדה", "משיכה", "עמלה"]
SECTORS = ["טכנולוגיה", "תקשורת", "צריכה מחזורית", "צריכה בסיסית", "בריאות",
           "פיננסים", "תעשייה", "אנרגיה", "חומרים", "נדל\"ן", "תשתיות", "ETF / מדד", "אחר"]

wb = Workbook()


def sheet(title, tab_color):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = tab_color
    return ws


def banner(ws, text, sub, last_col):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    c = ws.cell(1, 1, text)
    c.font = Font(name=FONT, size=18, bold=True, color="FFFFFF")
    c.fill = HEAD_FILL
    c.alignment = Alignment(horizontal="right", vertical="center", indent=1)
    s = ws.cell(2, 1, sub)
    s.font = Font(name=FONT, size=10, italic=True, color="5A6B85")
    s.alignment = Alignment(horizontal="right", vertical="center", indent=1)
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 20


def headers(ws, row, cols, inputs=()):
    """cols: list of (title, width). inputs: 1-based column indexes the user fills."""
    for i, (title, width) in enumerate(cols, 1):
        c = ws.cell(row, i, title)
        c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF" if i not in inputs else NAVY)
        c.fill = HEAD_FILL if i not in inputs else PatternFill("solid", fgColor=GOLD)
        c.alignment = CENTER
        c.border = BOX
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[row].height = 36
    ws.freeze_panes = ws.cell(row + 1, 2)


def style_rows(ws, first, last, ncols, fmts, inputs=()):
    for r in range(first, last + 1):
        for ci in range(1, ncols + 1):
            c = ws.cell(r, ci)
            c.font = Font(name=FONT, size=10, color="0000FF" if ci in inputs else "000000")
            c.border = BOX
            c.alignment = Alignment(horizontal="center", vertical="center")
            if ci in inputs:
                c.fill = INPUT_FILL
            if ci in fmts:
                c.number_format = fmts[ci]


def name(n, ref):
    wb.defined_names[n] = DefinedName(n, attr_text=ref)


# ───────────────────────── הוראות ─────────────────────────
ws = wb.active
ws.title = "הוראות"
ws.sheet_view.rightToLeft = True
ws.sheet_view.showGridLines = False
ws.sheet_properties.tabColor = GOLD
banner(ws, "Pearl Portfolio Tracker · מערכת ניהול תיק השקעות",
       "ניהול תיק, סיכונים, דיבידנדים וביצועים — בעברית, עם מחירים חיים ב-Google Sheets", 3)
ws.column_dimensions["A"].width = 4
ws.column_dimensions["B"].width = 26
ws.column_dimensions["C"].width = 100
guide = [
    ("איך מתחילים", None),
    ("1. הגדרות", "קבע % סיכון לעסקה, תקרת סיכון כוללת לתיק, ושער דולר. מכאן נגזרים גודל פוזיציה והתראות."),
    ("2. עסקאות", "כל תנועה בשורה אחת: הפקדה, קנייה, מכירה, דיבידנד, משיכה, עמלה. זה המקור היחיד לאמת — כל השאר מחושב מכאן."),
    ("3. תיק", "רשום כל טיקר פעם אחת (עמודה A), סקטור, סטופ התחלתי וסטופ נוכחי. כמות, עלות ממוצעת, רווח ו-R מחושבים לבד."),
    ("4. מעקב", "מניות שאתה שוקל: אזור כניסה, סטופ ויעדים. המערכת מחשבת כמה מניות לקנות לפי מדיניות הסיכון ומסמנת כשהמחיר באזור הכניסה."),
    ("5. ביצועים", "בסוף כל חודש הזן את שווי התיק (או השאר — החודש הנוכחי מתמלא לבד). מקבלים תשואה חודשית ומצטברת מנוטרלת הפקדות."),
    ("6. דשבורד", "תמונת מצב: שווי, רווח, דיבידנדים, חום התיק (סיכון כולל), התראות פעילות, פיזור סקטורים וגרפים."),
    ("", None),
    ("מקרא צבעים", None),
    ("תא צהוב / טקסט כחול", "שדה קלט — כאן מקלידים."),
    ("טקסט שחור", "נוסחה — לא לגעת."),
    ("כותרת זהובה", "עמודת קלט בטבלה."),
    ("", None),
    ("מחירים חיים", None),
    ("Google Sheets", "קובץ ← ייבוא ← העלה את הקובץ. עמודת \"מחיר\" משתמשת ב-GOOGLEFINANCE ומתעדכנת אוטומטית (עיכוב של עד 20 דק')."),
    ("Excel", "GOOGLEFINANCE לא קיים באקסל, ולכן נלקח המחיר מעמודת \"מחיר ידני\". עדכן אותה כשתרצה."),
    ("טיקרים", "מניות ארה\"ב: AAPL. ת\"א: TLV:TEVA. אם GOOGLEFINANCE לא מזהה טיקר — נלקח המחיר הידני."),
    ("", None),
    ("התראות בטבלת התיק", None),
    ("🔴 סטופ נפגע", "המחיר מתחת לסטופ — לצאת."),
    ("🟠 אין סטופ", "לפוזיציה לא הוגדר סטופ."),
    ("🟠 קרוב לסטופ", "נותרו פחות מסף הקרבה (ברירת מחדל 2%) עד הסטופ."),
    ("🟡 הזז לאיזון", "הרווח עבר 1R והסטופ עדיין מתחת לעלות — אפשר להעלות אותו לנקודת הכניסה ולהסיר סיכון."),
    ("🟢 מימוש חלקי", "הרווח עבר את סף ה-R למימוש (ברירת מחדל 3R)."),
    ("⚠️ סיכון חורג", "ההפסד האפשרי בפוזיציה גדול מ-% הסיכון לעסקה."),
    ("✅ תקין", "אין מה לעשות."),
    ("", None),
    ("הערות", None),
    ("עלות ממוצעת", "שיטת ממוצע משוקלל של כל הקניות עד אותה עסקה. רווח ממומש מחושב מול העלות הזו."),
    ("נתוני דוגמה", "השורות המסומנות \"דוגמה\" בעסקאות ובתיק — מחק אותן לפני שאתה מזין את התיק האמיתי."),
]
r = 4
for k, v in guide:
    if v is None and k:
        c = ws.cell(r, 2, k)
        c.font = Font(name=FONT, size=13, bold=True, color=NAVY)
        ws.cell(r, 3).fill = PatternFill("solid", fgColor=GOLD)
        ws.row_dimensions[r].height = 22
    elif k:
        ws.cell(r, 2, k).font = Font(name=FONT, size=10, bold=True)
        c = ws.cell(r, 3, v)
        c.font = Font(name=FONT, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right")
    r += 1
ws["B10"].fill = INPUT_FILL  # sample for the legend row "תא צהוב"
ws["B10"].font = Font(name=FONT, size=10, bold=True, color="0000FF")
ws["B12"].fill = PatternFill("solid", fgColor=GOLD)

# ───────────────────────── הגדרות ─────────────────────────
st = sheet("הגדרות", "7F8C8D")
banner(st, "⚙️ הגדרות", "כל ההנחות במקום אחד. התאים הצהובים הם שלך.", 3)
st.column_dimensions["A"].width = 34
st.column_dimensions["B"].width = 16
st.column_dimensions["C"].width = 70
settings = [
    ("RiskPct", "סיכון מרבי לעסקה (% מהתיק)", 0.01, PCT, "כלל אצבע: 1%. בתיק של $100,000 — הפסד מרבי של $1,000 לעסקה."),
    ("MaxHeat", "תקרת סיכון כוללת לתיק (חום)", 0.08, PCT, "סך ההפסד האפשרי אם כל הסטופים ייפגעו יחד."),
    ("NearStop", "סף \"קרוב לסטופ\"", 0.02, PCT, "מתחת למרחק הזה מהסטופ תופיע התראה."),
    ("PartialR", "R למימוש חלקי", 3, '0.0"R"', "מעל מכפיל רווח זה תוצע מכירה חלקית."),
    ("MaxPos", "גודל פוזיציה מרבי (% מהתיק)", 0.20, PCT, "תקרה לגודל פוזיציה חדשה, גם אם הסטופ צמוד."),
    ("EntryZone", "רוחב אזור כניסה ברשימת מעקב", 0.015, PCT, "מחיר עד X% מעל מחיר הכניסה נחשב \"באזור\"."),
    ("FxManual", "שער דולר-שקל ידני", 3.65, "0.000", "גיבוי לשער החי (משמש באקסל). עדכן מדי פעם."),
    ("Fx", "שער דולר-שקל בשימוש", '=IFERROR(GOOGLEFINANCE("CURRENCY:USDILS"),FxManual)', "0.000",
     "חי ב-Google Sheets, ידני באקסל."),
    ("DivYear", "שנת לוח הדיבידנדים", 2026, "0", "השנה שמוצגת בלשונית דיבידנדים."),
    ("PerfStart", "חודש התחלת מעקב ביצועים", date(2026, 1, 1), "mm/yyyy", "החודש הראשון בטבלת הביצועים (24 חודשים)."),
]
for i, (nm, label, val, fmt, note) in enumerate(settings, 4):
    st.cell(i, 1, label).font = Font(name=FONT, size=10, bold=True)
    c = st.cell(i, 2, val)
    c.number_format = fmt
    c.border = BOX
    c.alignment = Alignment(horizontal="center")
    is_input = not (isinstance(val, str) and val.startswith("="))
    c.font = Font(name=FONT, size=10, color="0000FF" if is_input else "000000")
    if is_input:
        c.fill = INPUT_FILL
    st.cell(i, 3, note).font = Font(name=FONT, size=9, color="5A6B85")
    name(nm, f"'הגדרות'!$B${i}")

st.cell(15, 1, "סקטורים").font = Font(name=FONT, size=12, bold=True, color=NAVY)
st.cell(15, 3, "רשימת הסקטורים לבחירה בטבלת התיק. אפשר לשנות שמות.").font = Font(name=FONT, size=9, color="5A6B85")
for i, s in enumerate(SECTORS, 16):
    c = st.cell(i, 1, s)
    c.font = Font(name=FONT, size=10, color="0000FF")
    c.fill = INPUT_FILL
    c.border = BOX
SEC_FIRST, SEC_LAST = 16, 16 + len(SECTORS) - 1
name("SectorList", f"'הגדרות'!$A${SEC_FIRST}:$A${SEC_LAST}")

# ───────────────────────── עסקאות ─────────────────────────
tx = sheet("עסקאות", "2E86DE")
banner(tx, "📒 יומן עסקאות", "כל תנועה בתיק בשורה אחת. מכאן מחושב הכול.", 11)
tx_cols = [("תאריך", 12), ("סוג", 11), ("טיקר", 10), ("כמות", 10), ("מחיר למניה $", 13),
           ("סכום $\n(דיבידנד/הפקדה/משיכה)", 17), ("עמלה $", 10), ("תזרים מזומן $", 14),
           ("עלות קנייה $", 14), ("רווח ממומש $", 14), ("הערות", 30)]
headers(tx, 4, tx_cols, inputs=(1, 2, 3, 4, 5, 6, 7, 11))
style_rows(tx, TX_FIRST, TX_LAST, 11,
           {1: DATE, 4: NUM, 5: USD, 6: USD, 7: USD, 8: USD, 9: USD, 10: USD},
           inputs=(1, 2, 3, 4, 5, 6, 7, 11))
for r in range(TX_FIRST, TX_LAST + 1):
    tx.cell(r, 8, f'=IF(B{r}="","",IF(B{r}="קנייה",-(D{r}*E{r}+G{r}),IF(B{r}="מכירה",D{r}*E{r}-G{r},'
                  f'IF(B{r}="דיבידנד",F{r}-G{r},IF(B{r}="הפקדה",F{r}-G{r},IF(B{r}="משיכה",-F{r}-G{r},-G{r}))))))')
    tx.cell(r, 9, f'=IF(B{r}="קנייה",D{r}*E{r}+G{r},0)')
    tx.cell(r, 10, f'=IF(B{r}="מכירה",D{r}*E{r}-G{r}-D{r}*IFERROR(SUMIFS($I${TX_FIRST}:I{r},$C${TX_FIRST}:C{r},C{r})/'
                   f'SUMIFS($D${TX_FIRST}:D{r},$C${TX_FIRST}:C{r},C{r},$B${TX_FIRST}:B{r},"קנייה"),0),0)')
    tx.cell(r, 10).font = Font(name=FONT, size=10, bold=True)
dv = DataValidation(type="list", formula1='"' + ",".join(TYPES) + '"', allow_blank=True,
                    showErrorMessage=True, errorTitle="סוג לא חוקי", error="בחר מהרשימה")
tx.add_data_validation(dv)
dv.add(f"B{TX_FIRST}:B{TX_LAST}")
tx.conditional_formatting.add(f"J{TX_FIRST}:J{TX_LAST}",
                              CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="1E8449", bold=True)))
tx.conditional_formatting.add(f"A{TX_FIRST}:K{TX_LAST}",
                              FormulaRule(formula=[f'$B{TX_FIRST}="מכירה"'], fill=PatternFill("solid", fgColor="FDEDEC")))
tx.conditional_formatting.add(f"A{TX_FIRST}:K{TX_LAST}",
                              FormulaRule(formula=[f'$B{TX_FIRST}="דיבידנד"'], fill=PatternFill("solid", fgColor="E9F7EF")))
tx["H4"].comment = Comment("פלוס = כסף נכנס לחשבון, מינוס = כסף יוצא. הסכום הוא יתרת המזומן.", "Pearl")
tx["J4"].comment = Comment("למכירות בלבד: תמורה פחות עמלה פחות כמות × עלות ממוצעת של הקניות עד אותה שורה.", "Pearl")
tx["F4"].comment = Comment("לדיבידנד: הסכום נטו שהתקבל (אחרי מס במקור). להפקדה/משיכה: הסכום.", "Pearl")

# נתוני דוגמה — מסומנים למחיקה
D = date
sample_tx = [
    (D(2026, 1, 2), "הפקדה", None, None, None, 100000, 0),
    (D(2026, 1, 5), "קנייה", "AAPL", 60, 185.0, None, 2.5),
    (D(2026, 1, 5), "קנייה", "MSFT", 30, 410.0, None, 2.5),
    (D(2026, 1, 12), "קנייה", "NVDA", 100, 120.0, None, 2.5),
    (D(2026, 2, 3), "קנייה", "KO", 150, 62.0, None, 2.5),
    (D(2026, 2, 17), "קנייה", "SPY", 25, 580.0, None, 2.5),
    (D(2026, 3, 9), "קנייה", "AAPL", 20, 172.0, None, 2.5),
    (D(2026, 4, 1), "דיבידנד", "KO", None, None, 65.03, 0),
    (D(2026, 5, 14), "דיבידנד", "AAPL", None, None, 17.0, 0),
    (D(2026, 6, 10), "מכירה", "NVDA", 40, 165.0, None, 2.5),
    (D(2026, 7, 1), "דיבידנד", "KO", None, None, 65.03, 0),
    (D(2026, 7, 2), "הפקדה", None, None, None, 10000, 0),
    (D(2026, 8, 13), "דיבידנד", "AAPL", None, None, 17.6, 0),
    (D(2026, 9, 11), "דיבידנד", "MSFT", None, None, 21.0, 0),
]
for i, row in enumerate(sample_tx, TX_FIRST):
    for ci, v in enumerate(row, 1):
        if v is not None:
            tx.cell(i, ci, v)
    tx.cell(i, 11, "דוגמה — למחיקה")

TXR = lambda col: f"'עסקאות'!${col}${TX_FIRST}:${col}${TX_LAST}"

# ───────────────────────── תיק ─────────────────────────
pf = sheet("תיק", "27AE60")
banner(pf, "💼 התיק שלי", "רשום טיקר, סקטור וסטופים — כל השאר מחושב מיומן העסקאות.", 23)
pf_cols = [("טיקר", 10), ("שם", 16), ("סקטור", 14), ("כמות", 9), ("עלות ממוצעת $", 12),
           ("מחיר ידני $", 11), ("מחיר $", 11), ("שווי שוק $", 13), ("עלות $", 13),
           ("רווח לא ממומש $", 14), ("רווח %", 9), ("משקל בתיק", 9), ("משקל יעד", 9),
           ("איזון $\n(+קנה / −מכור)", 13), ("סטופ התחלתי $", 11), ("סטופ נוכחי $", 11),
           ("מרחק לסטופ", 10), ("R", 8), ("סיכון להון $", 12), ("סיכון % מהתיק", 10),
           ("רווח ממומש $", 13), ("דיבידנדים $", 12), ("פעולה", 18)]
PF_IN = (1, 2, 3, 6, 13, 15, 16)
headers(pf, 4, pf_cols, inputs=PF_IN)
style_rows(pf, H_FIRST, H_LAST, 23,
           {4: NUM, 5: USD, 6: USD, 7: USD, 8: USD0, 9: USD0, 10: USD0, 11: PCT, 12: PCT, 13: PCT,
            14: USD0, 15: USD, 16: USD, 17: PCT, 18: RMULT, 19: USD0, 20: PCT, 21: USD0, 22: USD0},
           inputs=PF_IN)
for r in range(H_FIRST, H_LAST + 1):
    f = {
        4: f'=IF(A{r}="","",SUMIFS({TXR("D")},{TXR("C")},A{r},{TXR("B")},"קנייה")-SUMIFS({TXR("D")},{TXR("C")},A{r},{TXR("B")},"מכירה"))',
        5: f'=IF(A{r}="","",IFERROR(SUMIFS({TXR("I")},{TXR("C")},A{r})/SUMIFS({TXR("D")},{TXR("C")},A{r},{TXR("B")},"קנייה"),0))',
        7: f'=IF(A{r}="","",IFERROR(GOOGLEFINANCE(A{r}),F{r}))',
        8: f'=IF(A{r}="",0,D{r}*G{r})',
        9: f'=IF(A{r}="",0,D{r}*E{r})',
        10: f'=IF(A{r}="",0,H{r}-I{r})',
        11: f'=IF(I{r}=0,"",J{r}/I{r})',
        12: f'=IF(Equity=0,"",H{r}/Equity)',
        14: f'=IF(OR(A{r}="",M{r}=""),"",M{r}*Equity-H{r})',
        17: f'=IF(OR(A{r}="",P{r}="",G{r}=0),"",(G{r}-P{r})/G{r})',
        18: f'=IF(OR(A{r}="",O{r}="",E{r}<=O{r}),"",(G{r}-E{r})/(E{r}-O{r}))',
        19: f'=IF(OR(A{r}="",P{r}=""),0,MAX(0,E{r}-P{r})*D{r})',
        20: f'=IF(Equity=0,"",S{r}/Equity)',
        21: f'=IF(A{r}="",0,SUMIFS({TXR("J")},{TXR("C")},A{r}))',
        22: f'=IF(A{r}="",0,SUMIFS({TXR("F")},{TXR("C")},A{r},{TXR("B")},"דיבידנד"))',
        23: (f'=IF(OR(A{r}="",D{r}<=0),"",IF(P{r}="","🟠 אין סטופ",IF(G{r}<=P{r},"🔴 סטופ נפגע",'
             f'IF(Q{r}<NearStop,"🟠 קרוב לסטופ",IF(AND(R{r}<>"",R{r}>=PartialR),"🟢 מימוש חלקי",'
             f'IF(AND(R{r}<>"",R{r}>=1,P{r}<E{r}),"🟡 הזז לאיזון",IF(T{r}>RiskPct,"⚠️ סיכון חורג","✅ תקין")))))))'),
    }
    for ci, formula in f.items():
        pf.cell(r, ci, formula)
    pf.cell(r, 24, f'=IF(AND(W{r}<>"",W{r}<>"✅ תקין"),MAX($X${H_FIRST - 1}:X{r - 1})+1,"")')
    pf.cell(r, 24).font = Font(name=FONT, size=8, color="A0A0A0")
    pf.cell(r, 23).alignment = Alignment(horizontal="right", vertical="center", indent=1)
    pf.cell(r, 1).font = Font(name=FONT, size=10, bold=True, color="0000FF")

TOT = H_LAST + 1
pf.cell(TOT, 1, "סה\"כ").font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
for ci in range(1, 24):
    c = pf.cell(TOT, ci)
    c.fill = HEAD_FILL
    c.border = BOX
    c.alignment = CENTER
for ci, fmt in {8: USD0, 9: USD0, 10: USD0, 12: PCT, 13: PCT, 19: USD0, 20: PCT, 21: USD0, 22: USD0}.items():
    col = get_column_letter(ci)
    c = pf.cell(TOT, ci, f"=SUM({col}{H_FIRST}:{col}{H_LAST})")
    c.number_format = fmt
    c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
pf.cell(TOT, 11, f"=IF(I{TOT}=0,\"\",J{TOT}/I{TOT})").number_format = PCT
pf.cell(TOT, 11).font = Font(name=FONT, size=10, bold=True, color="FFFFFF")

dvs = DataValidation(type="list", formula1="=SectorList", allow_blank=True)
pf.add_data_validation(dvs)
dvs.add(f"C{H_FIRST}:C{H_LAST}")
for col in ("J", "K", "R", "U"):
    rng = f"{col}{H_FIRST}:{col}{H_LAST}"
    pf.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="1E8449", bold=True)))
    pf.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], font=Font(color="C0392B", bold=True)))
act = f"W{H_FIRST}:W{H_LAST}"
for key, color in (("🔴", "F5B7B1"), ("🟠", "FAD7A0"), ("🟡", "FCF3CF"), ("🟢", "ABEBC6"), ("⚠️", "F9E79F")):
    pf.conditional_formatting.add(act, FormulaRule(formula=[f'LEFT($W{H_FIRST},{len(key)})="{key}"'],
                                                   fill=PatternFill("solid", fgColor=color)))
pf.conditional_formatting.add(f"Q{H_FIRST}:Q{H_LAST}",
                              FormulaRule(formula=[f'AND(ISNUMBER(Q{H_FIRST}),Q{H_FIRST}<NearStop)'],
                                          fill=PatternFill("solid", fgColor="FAD7A0")))
pf["G4"].comment = Comment("ב-Google Sheets: GOOGLEFINANCE חי. באקסל: המחיר הידני.", "Pearl")
pf["R4"].comment = Comment("רווח ביחידות הסיכון המקורי: (מחיר − עלות) ÷ (עלות − סטופ התחלתי). 2R = הרווחת פי 2 ממה שסיכנת.", "Pearl")
pf["S4"].comment = Comment("כמה מההון תפסיד אם הסטופ הנוכחי ייפגע. 0 כשהסטופ מעל העלות (העסקה \"חינם\").", "Pearl")
pf["N4"].comment = Comment("כמה דולר לקנות (+) או למכור (−) כדי להגיע למשקל היעד.", "Pearl")

sample_pf = [
    ("AAPL", "Apple", "טכנולוגיה", 232.0, 0.15, 170.0, 205.0),
    ("MSFT", "Microsoft", "טכנולוגיה", 455.0, 0.15, 380.0, 400.0),
    ("NVDA", "Nvidia", "טכנולוגיה", 178.0, 0.12, 105.0, 150.0),
    ("KO", "Coca-Cola", "צריכה בסיסית", 68.5, 0.10, 58.0, 59.0),
    ("SPY", "S&P 500 ETF", "ETF / מדד", 655.0, 0.30, 545.0, None),
]
for i, (t, n, s, p, tw, s0, s1) in enumerate(sample_pf, H_FIRST):
    pf.cell(i, 1, t)
    pf.cell(i, 2, n)
    pf.cell(i, 3, s)
    pf.cell(i, 6, p)
    pf.cell(i, 13, tw)
    pf.cell(i, 15, s0)
    if s1 is not None:
        pf.cell(i, 16, s1)

pf.cell(4, 24, "#").font = Font(name=FONT, size=8, color="A0A0A0")
pf.column_dimensions["X"].hidden = True

PFR = lambda col: f"'תיק'!${col}${H_FIRST}:${col}${H_LAST}"

# ───────────────────────── דשבורד ─────────────────────────
db = sheet("דשבורד", NAVY)
banner(db, "🎯 Pearl Portfolio · דשבורד", "תמונת מצב של התיק — מתעדכן אוטומטית.", 12)
for col, w in zip("ABCDEFGHIJKL", (3, 20, 16, 3, 20, 16, 3, 20, 16, 3, 18, 14)):
    db.column_dimensions[col].width = w

name("Cash", "'דשבורד'!$C$8")
name("Equity", "'דשבורד'!$C$5")
kpis = [
    # (row, col, label, formula, fmt)
    (5, 2, "שווי תיק כולל $", "=C6+C8", USD0),
    (6, 2, "שווי מניות $", f"=SUM({PFR('H')})", USD0),
    (7, 2, "שווי כולל ₪", "=C5*Fx", '₪#,##0'),
    (8, 2, "מזומן $", f"=SUM({TXR('H')})", USD0),
    (5, 5, "הון שהופקד נטו $", f'=SUMIFS({TXR("F")},{TXR("B")},"הפקדה")-SUMIFS({TXR("F")},{TXR("B")},"משיכה")', USD0),
    (6, 5, "רווח כולל $", "=C5-F5", USD0),
    (7, 5, "תשואה כוללת", "=IF(F5=0,\"\",F6/F5)", PCT),
    (8, 5, "רווח לא ממומש $", f"=SUM({PFR('J')})", USD0),
    (5, 8, "רווח ממומש $", f"=SUM({TXR('J')})", USD0),
    (6, 8, "דיבידנדים מצטברים $", f'=SUMIFS({TXR("F")},{TXR("B")},"דיבידנד")', USD0),
    (7, 8, "דיבידנד שנתי צפוי $", "=IFERROR(IF(TODAY()-MIN(" + TXR("A") + ")<30,I6,I6*365/(TODAY()-MIN(" + TXR("A") + "))),0)", USD0),
    (8, 8, "עמלות ששולמו $", f"=SUM({TXR('G')})", USD0),
    (5, 11, "חום התיק (סיכון כולל)", f"=IF(C5=0,\"\",SUM({PFR('S')})/C5)", PCT),
    (6, 11, "תקרת חום", "=MaxHeat", PCT),
    (7, 11, "פוזיציות פתוחות", f'=COUNTIF({PFR("D")},">0")', "0"),
    (8, 11, "התראות פעילות", f'=COUNTIF({PFR("W")},"🔴*")+COUNTIF({PFR("W")},"🟠*")+COUNTIF({PFR("W")},"🟡*")+COUNTIF({PFR("W")},"🟢*")+COUNTIF({PFR("W")},"⚠️*")', "0"),
]
for r0 in (4,):
    for c0, title in ((2, "שווי"), (5, "רווח"), (8, "הכנסות ועלויות"), (11, "סיכון")):
        db.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + 1)
        c = db.cell(r0, c0, title)
        c.font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=GOLD)
        c.alignment = CENTER
for (r, c, label, formula, fmt) in kpis:
    l = db.cell(r, c, label)
    l.font = Font(name=FONT, size=10, color="5A6B85")
    l.fill = KPI_FILL
    l.border = BOX
    l.alignment = Alignment(horizontal="right", vertical="center", indent=1)
    v = db.cell(r, c + 1, formula)
    v.font = Font(name=FONT, size=13, bold=True, color=NAVY)
    v.fill = KPI_FILL
    v.border = BOX
    v.number_format = fmt
    v.alignment = CENTER
    db.row_dimensions[r].height = 26
db["I7"].comment = Comment("קצב הדיבידנדים שהתקבלו עד היום, מנורמל לשנה.", "Pearl")
db["L5"].comment = Comment("סך ההפסד האפשרי (סיכון להון) אם כל הסטופים ייפגעו, באחוזים מהתיק.", "Pearl")
for rng in ("F6", "F7", "F8", "I5"):
    db.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="1E8449", bold=True, size=13)))
    db.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], font=Font(color="C0392B", bold=True, size=13)))
db.conditional_formatting.add("L5", FormulaRule(formula=["AND(ISNUMBER(L5),L5>MaxHeat)"],
                                                fill=PatternFill("solid", fgColor="F5B7B1")))
db.conditional_formatting.add("L8", CellIsRule(operator="greaterThan", formula=["0"],
                                               fill=PatternFill("solid", fgColor="FAD7A0")))

# פיזור סקטורים
SR = 11
for ci, t in ((2, "סקטור"), (3, "שווי $"), (4, ""), (5, "משקל")):
    c = db.cell(SR, ci, t)
    c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
    c.fill = HEAD_FILL
    c.alignment = CENTER
db.cell(SR - 1, 2, "פיזור לפי סקטור").font = Font(name=FONT, size=12, bold=True, color=NAVY)
for i in range(len(SECTORS)):
    r = SR + 1 + i
    db.cell(r, 2, f"='הגדרות'!A{SEC_FIRST + i}")
    db.cell(r, 3, f"=SUMIFS({PFR('H')},{PFR('C')},B{r})").number_format = USD0
    db.cell(r, 5, f"=IF($C$6=0,\"\",C{r}/$C$6)").number_format = PCT
    for ci in (2, 3, 5):
        db.cell(r, ci).font = Font(name=FONT, size=10)
        db.cell(r, ci).border = BOX
SEC_END = SR + len(SECTORS)
db.conditional_formatting.add(f"E{SR + 1}:E{SEC_END}",
                              FormulaRule(formula=[f"AND(ISNUMBER(E{SR + 1}),E{SR + 1}>0)"],
                                          fill=PatternFill("solid", fgColor="E8EDF5")))

# פוזיציות שדורשות טיפול (משיכה ישירה של 10 השורות הראשונות עם התראה)
db.cell(SR - 1, 8, "התראות לפי פוזיציה").font = Font(name=FONT, size=12, bold=True, color=NAVY)
for ci, t in ((8, "טיקר"), (9, "פעולה")):
    c = db.cell(SR, ci, t)
    c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
    c.fill = HEAD_FILL
    c.alignment = CENTER
db.merge_cells(start_row=SR, start_column=9, end_row=SR, end_column=12)
for k in range(1, 11):
    r = SR + k
    # הטיקר ה-k שיש לו התראה פעילה (לפי עמודת העזר X בתיק)
    db.cell(r, 8, f'=IFERROR(INDEX({PFR("A")},MATCH({k},{PFR("X")},0)),"")')
    db.cell(r, 9, f'=IF(H{r}="","",INDEX({PFR("W")},MATCH(H{r},{PFR("A")},0)))')
    db.merge_cells(start_row=r, start_column=9, end_row=r, end_column=12)
    for ci in (8, 9):
        db.cell(r, ci).font = Font(name=FONT, size=10, bold=(ci == 8))
        db.cell(r, ci).border = BOX
        db.cell(r, ci).alignment = Alignment(horizontal="right", vertical="center", indent=1)

# ───────────────────────── מעקב ─────────────────────────
wl = sheet("מעקב", "8E44AD")
banner(wl, "👁️ רשימת מעקב ותכנון כניסות", "הגדר כניסה, סטופ ויעדים — המערכת מחשבת גודל פוזיציה לפי מדיניות הסיכון.", 18)
wl_cols = [("טיקר", 10), ("שם", 16), ("סטאפ / סיבה", 22), ("מחיר ידני $", 11), ("מחיר $", 11),
           ("כניסה $", 10), ("סטופ $", 10), ("יעד 1 $", 10), ("יעד 2 $", 10), ("סיכון למניה $", 11),
           ("סיכוי:סיכון\n(יעד 1)", 11), ("כמות מניות\nלפי סיכון", 11), ("גודל פוזיציה $", 13),
           ("% מהתיק", 9), ("מרחק לכניסה", 10), ("רווח ביעד 1 $", 12), ("הפסד בסטופ $", 12), ("סטטוס", 16)]
WL_IN = (1, 2, 3, 4, 6, 7, 8, 9)
headers(wl, 4, wl_cols, inputs=WL_IN)
style_rows(wl, W_FIRST, W_LAST, 18,
           {4: USD, 5: USD, 6: USD, 7: USD, 8: USD, 9: USD, 10: USD, 11: '0.0":1"', 12: "#,##0",
            13: USD0, 14: PCT, 15: PCT, 16: USD0, 17: USD0}, inputs=WL_IN)
for r in range(W_FIRST, W_LAST + 1):
    f = {
        5: f'=IF(A{r}="","",IFERROR(GOOGLEFINANCE(A{r}),D{r}))',
        10: f'=IF(OR(F{r}="",G{r}="",F{r}<=G{r}),"",F{r}-G{r})',
        11: f'=IF(OR(J{r}="",H{r}=""),"",(H{r}-F{r})/J{r})',
        12: f'=IF(J{r}="","",MIN(ROUNDDOWN(Equity*RiskPct/J{r},0),ROUNDDOWN(Equity*MaxPos/F{r},0),ROUNDDOWN(MAX(0,Cash)/F{r},0)))',
        13: f'=IF(L{r}="","",L{r}*F{r})',
        14: f'=IF(OR(M{r}="",Equity=0),"",M{r}/Equity)',
        15: f'=IF(OR(E{r}="",F{r}=""),"",E{r}/F{r}-1)',
        16: f'=IF(OR(L{r}="",H{r}=""),"",L{r}*(H{r}-F{r}))',
        17: f'=IF(L{r}="","",-L{r}*J{r})',
        18: (f'=IF(OR(A{r}="",F{r}=""),"",IF(E{r}<=G{r},"⛔ מתחת לסטופ",IF(E{r}<=F{r}*(1+EntryZone),'
             f'IF(AND(K{r}<>"",K{r}<2),"🟡 באזור — R:R נמוך","🟢 באזור כניסה"),"⏳ ממתין")))'),
    }
    for ci, formula in f.items():
        wl.cell(r, ci, formula)
    wl.cell(r, 1).font = Font(name=FONT, size=10, bold=True, color="0000FF")
    wl.cell(r, 18).alignment = Alignment(horizontal="right", vertical="center", indent=1)
wst = f"R{W_FIRST}:R{W_LAST}"
for key, color in (("🟢", "ABEBC6"), ("🟡", "FCF3CF"), ("⛔", "F5B7B1")):
    wl.conditional_formatting.add(wst, FormulaRule(formula=[f'LEFT($R{W_FIRST},{len(key)})="{key}"'],
                                                   fill=PatternFill("solid", fgColor=color)))
wl.conditional_formatting.add(f"K{W_FIRST}:K{W_LAST}",
                              CellIsRule(operator="greaterThanOrEqual", formula=["2"], font=Font(color="1E8449", bold=True)))
wl["L4"].comment = Comment("כמות שמגבילה את ההפסד בסטופ ל-% הסיכון לעסקה, בלי לחרוג מגודל הפוזיציה המרבי ומהמזומן הפנוי.", "Pearl")
wl["K4"].comment = Comment("כמה R מרוויחים ביעד הראשון. מתחת ל-2 — עסקה פחות כדאית.", "Pearl")
for i, row in enumerate([
    ("AMZN", "Amazon", "תיקון לממוצע 50", 228.0, 225.0, 214.0, 250.0, 270.0),
    ("GOOGL", "Alphabet", "פריצת שיא 20 יום", 245.0, 240.0, 228.0, 270.0, 290.0),
], W_FIRST):
    for ci, v in zip(WL_IN, row):
        wl.cell(i, ci, v)

# ───────────────────────── דיבידנדים ─────────────────────────
dv_ws = sheet("דיבידנדים", "F39C12")
banner(dv_ws, "💰 לוח דיבידנדים", "דיבידנדים נטו שהתקבלו לפי מניה וחודש. שנה: ראה הגדרות.", 15)
months = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ"]
dv_cols = [("טיקר", 10)] + [(m, 9) for m in months] + [("סה\"כ שנה", 11), ("תשואה על עלות", 11)]
headers(dv_ws, 4, dv_cols)
dv_ws.cell(3, 1, "שנה:").font = Font(name=FONT, size=10, bold=True)
dv_ws.cell(3, 2, "=DivYear").font = Font(name=FONT, size=10, bold=True, color="008000")
DV_LAST = H_FIRST + (H_LAST - H_FIRST)
style_rows(dv_ws, H_FIRST, DV_LAST, 15, {**{c: USD for c in range(2, 15)}, 15: PCT})
for r in range(H_FIRST, DV_LAST + 1):
    dv_ws.cell(r, 1, f"=IF('תיק'!A{r}=\"\",\"\",'תיק'!A{r})").font = Font(name=FONT, size=10, bold=True, color="008000")
    for m in range(1, 13):
        dv_ws.cell(r, m + 1, (f'=IF($A{r}="",0,SUMPRODUCT(({TXR("B")}="דיבידנד")*({TXR("C")}=$A{r})*'
                              f'(YEAR({TXR("A")})=DivYear)*(MONTH({TXR("A")})={m})*{TXR("F")}))'))
    dv_ws.cell(r, 14, f"=SUM(B{r}:M{r})").font = Font(name=FONT, size=10, bold=True)
    dv_ws.cell(r, 15, f"=IF(OR(A{r}=\"\",'תיק'!I{r}=0),\"\",N{r}/'תיק'!I{r})")
DT = DV_LAST + 1
dv_ws.cell(DT, 1, "סה\"כ")
for ci in range(1, 16):
    c = dv_ws.cell(DT, ci)
    c.fill = HEAD_FILL
    c.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
    c.alignment = CENTER
for ci in range(2, 15):
    col = get_column_letter(ci)
    dv_ws.cell(DT, ci, f"=SUM({col}{H_FIRST}:{col}{DV_LAST})").number_format = USD0
dv_ws.cell(DT + 1, 1, "מצטבר").font = Font(name=FONT, size=10, bold=True)
for ci in range(2, 14):
    col, prev = get_column_letter(ci), get_column_letter(ci - 1)
    c = dv_ws.cell(DT + 1, ci, f"={col}{DT}" if ci == 2 else f"={prev}{DT + 1}+{col}{DT}")
    c.number_format = USD0
    c.font = Font(name=FONT, size=10)
for ci in range(2, 14):
    dv_ws.cell(DT + 2, ci, months[ci - 2])  # תוויות לגרף
    dv_ws.cell(DT + 2, ci).font = Font(name=FONT, size=8, color="FFFFFF")
dv_ws.conditional_formatting.add(f"B{H_FIRST}:M{DV_LAST}",
                                 CellIsRule(operator="greaterThan", formula=["0"],
                                            fill=PatternFill("solid", fgColor="E9F7EF"), font=Font(color="1E8449", bold=True)))

# ───────────────────────── ביצועים ─────────────────────────
pr = sheet("ביצועים", "C0392B")
banner(pr, "📈 ביצועים חודשיים", "הזן שווי תיק בסוף כל חודש. התשואה מנוטרלת מהפקדות ומשיכות.", 9)
pr_cols = [("חודש", 11), ("הפקדות נטו $", 13), ("דיבידנדים $", 12), ("רווח ממומש $", 13),
           ("שווי סוף חודש $\n(קלט)", 15), ("שווי בשימוש $", 14), ("תשואה חודשית", 11),
           ("תשואה מצטברת", 11), ("רווח בחודש $", 13)]
headers(pr, 4, pr_cols, inputs=(5,))
P_FIRST, P_LAST = 5, 28
style_rows(pr, P_FIRST, P_LAST, 9, {1: "mm/yyyy", 2: USD0, 3: USD0, 4: USD0, 5: USD0, 6: USD0,
                                     7: PCT, 8: PCT, 9: USD0}, inputs=(5,))
for r in range(P_FIRST, P_LAST + 1):
    pr.cell(r, 1, "=PerfStart" if r == P_FIRST else f"=EDATE(A{r - 1},1)")
    inmonth = f'({TXR("A")}>=A{r})*({TXR("A")}<EDATE(A{r},1))'
    pr.cell(r, 2, f'=SUMPRODUCT({inmonth}*({TXR("B")}="הפקדה")*{TXR("F")})-SUMPRODUCT({inmonth}*({TXR("B")}="משיכה")*{TXR("F")})')
    pr.cell(r, 3, f'=SUMPRODUCT({inmonth}*({TXR("B")}="דיבידנד")*{TXR("F")})')
    pr.cell(r, 4, f'=SUMPRODUCT({inmonth}*{TXR("J")})')
    # החודש הנוכחי מתמלא אוטומטית משווי התיק החי
    pr.cell(r, 6, f'=IF(E{r}<>"",E{r},IF(AND(TODAY()>=A{r},TODAY()<EDATE(A{r},1)),Equity,""))')
    prev = "0" if r == P_FIRST else f"F{r - 1}"
    blank = f'F{r}=""' if r == P_FIRST else f'OR(F{r}="",F{r - 1}="")'
    pr.cell(r, 7, f'=IF({blank},"",IF(({prev}+B{r})=0,"",(F{r}-{prev}-B{r})/({prev}+B{r})))')
    cum = f"G{r}" if r == P_FIRST else f'(1+IF(H{r - 1}="",0,H{r - 1}))*(1+G{r})-1'
    pr.cell(r, 8, f'=IF(G{r}="","",{cum})')
    pr.cell(r, 9, f'=IF({blank},"",F{r}-{prev}-B{r})')
pr.conditional_formatting.add(f"G{P_FIRST}:I{P_LAST}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="1E8449", bold=True)))
pr.conditional_formatting.add(f"G{P_FIRST}:I{P_LAST}", CellIsRule(operator="lessThan", formula=["0"], font=Font(color="C0392B", bold=True)))
pr["G4"].comment = Comment("(שווי סוף − שווי קודם − הפקדות נטו) ÷ (שווי קודם + הפקדות נטו). הפקדות נחשבות בתחילת החודש.", "Pearl")
for i, v in enumerate([101200, 103900, 102100, 106800, 109300, 112050, 123400, 126900, 124800], P_FIRST):
    pr.cell(i, 5, v)

# ───────────────────────── גרפים ─────────────────────────
pie = PieChart()
pie.title = "הרכב התיק"
pie.add_data(Reference(pf, min_col=8, min_row=4, max_row=H_LAST), titles_from_data=True)
pie.set_categories(Reference(pf, min_col=1, min_row=H_FIRST, max_row=H_LAST))
pie.dataLabels = DataLabelList()
pie.dataLabels.showPercent = True
pie.height, pie.width = 9, 13
db.add_chart(pie, "B27")

sec = PieChart()
sec.title = "פיזור סקטורים"
sec.add_data(Reference(db, min_col=3, min_row=SR, max_row=SEC_END), titles_from_data=True)
sec.set_categories(Reference(db, min_col=2, min_row=SR + 1, max_row=SEC_END))
sec.dataLabels = DataLabelList()
sec.dataLabels.showPercent = True
sec.height, sec.width = 9, 13
db.add_chart(sec, "F27")

bar = BarChart()
bar.type = "bar"
bar.title = "רווח לא ממומש לפי מניה"
bar.add_data(Reference(pf, min_col=10, min_row=4, max_row=H_FIRST + 9), titles_from_data=True)
bar.set_categories(Reference(pf, min_col=1, min_row=H_FIRST, max_row=H_FIRST + 9))
bar.legend = None
bar.height, bar.width = 9, 13
db.add_chart(bar, "J27")

line = LineChart()
line.title = "שווי התיק לאורך זמן"
line.add_data(Reference(pr, min_col=6, min_row=4, max_row=P_LAST), titles_from_data=True)
line.set_categories(Reference(pr, min_col=1, min_row=P_FIRST, max_row=P_LAST))
line.legend = None
line.height, line.width = 9, 20
db.add_chart(line, "B46")

perf_bar = BarChart()
perf_bar.title = "תשואה חודשית"
perf_bar.add_data(Reference(pr, min_col=7, min_row=4, max_row=P_LAST), titles_from_data=True)
perf_bar.set_categories(Reference(pr, min_col=1, min_row=P_FIRST, max_row=P_LAST))
perf_bar.legend = None
perf_bar.height, perf_bar.width = 9, 14
db.add_chart(perf_bar, "I46")

div_bar = BarChart()
div_bar.title = "דיבידנדים לפי חודש"
div_bar.add_data(Reference(dv_ws, min_col=2, max_col=13, min_row=DT, max_row=DT), from_rows=True)
div_bar.set_categories(Reference(dv_ws, min_col=2, max_col=13, min_row=DT + 2, max_row=DT + 2))
div_bar.legend = None
div_bar.height, div_bar.width = 8, 18
dv_ws.add_chart(div_bar, "B60")

# סדר לשוניות: הוראות, דשבורד, תיק, עסקאות, מעקב, דיבידנדים, ביצועים, הגדרות
order = ["הוראות", "דשבורד", "תיק", "עסקאות", "מעקב", "דיבידנדים", "ביצועים", "הגדרות"]
wb._sheets = [wb[n] for n in order]
wb.active = 1
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print(f"saved {OUT}")
