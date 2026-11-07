# 📰 חדר החדשות

מערכת חדשות והתראות אישית לשוק ההון האמריקאי: התראות חכמות בטלגרם, ארבע מהדורות קבועות ודשבורד ויזואלי.
רצה לבד ב-GitHub Actions. אין שרת, ואין עלות.

> הפרויקט עצמאי לגמרי. התיקייה הזו (`newsroom/`) היא שורש ה-repo שלו, ואין לה שום קשר לאתר ניתוח המניות.

---

## מה יש בפנים

| | מה | מתי |
|---|---|---|
| 📲 | **התראות**: תנועה חריגה ביחס לתנודתיות של כל נייר, תנועות בשוק כולו, דוחות, 8-K, נתוני מאקרו, החלטת ריבית, "סיפור חם" | כל 15 דקות בשעות המסחר |
| ☀️ | **מהדורת בוקר** (9 סעיפים) | 07:00 שעון ישראל, שני עד שבת |
| 🔔 | **לפני הפתיחה**: פרה-מרקט, חוזים, מאקרו ודוחות מהבוקר | 30 דקות לפני הפתיחה בניו יורק |
| 🌆 | **סיכום סגירה** (בלי צליל) | כ-15 דקות אחרי הסגירה |
| 📅 | **סיכום שבועי** (כתוב כך שאפשר להפוך אותו לפוסט) | ראשון 08:00 |
| 🎨 | **דשבורד**: מזג האוויר בשוק, מפת חום, גרף עם סיכות חדשות, "מה הזיז את השוק", נהר הסיפורים, שרשרת ההשפעה, קו הרכבת של השבוע, חפיפת MAGS | מתעדכן כל 10 דקות |

### איך זה עובד
```
GitHub Actions (cron, UTC)  ──►  python -m newsroom tick
   1. פקודות מהבוט (/add, /remove, /pause ...)          ← רק מה-chat_id שלך
   2. איזו מהדורה מגיעה עכשיו? (שעון ישראל/ניו יורק, חגים, ימים מקוצרים)
   3. איסוף: Finnhub · Tiingo · FRED · SEC · Fed · CoinGecko · RSS (+ Yahoo כגיבוי)
   4. קיבוץ כותרות לסיפורים ← ציון חשיבות 1–10 ← זיהוי התראות
   5. Gemini כותב רק משפטים. כל מספר נבדק מול הנתונים, ומשפט עם מספר מומצא נמחק.
   6. נגד רעש: כפילויות, צינון של שעתיים, תקרה יומית, שעות שקט, השהיה
   7. שליחה לטלגרם · עדכון הדשבורד (Cloudflare KV)
   8. שמירת מצב לענף data (commit יחיד, ה-repo לא מתנפח)
```

### כללי ברזל במערכת
- **מספרים מגיעים מה-API, לא ממודל השפה.** בדיקה אוטומטית פוסלת כל משפט עם מספר שלא היה בנתונים.
- **אין המלצות.** אין "קנה" או "מכור". יש "למה זה חשוב".
- **סיכום, לא העתקה.** נשמרים רק כותרת, קישור, מקור ושעה. הארכיון נמחק אחרי 90 יום.
- **המערכת לא שותקת.** מקור נפל? המהדורה יוצאת בלעדיו ומציינת את זה. המודל נפל? יוצאת מהדורה מתבנית. חלק אחד נכשל? השאר רצים, ומגיעה הודעת "⚠️ המערכת נתקלה בתקלה".

---

## 🛠 הקמה, צעד אחר צעד

### 1. repo חדש ב-GitHub
1. https://github.com/new ← Repository name: `newsroom` ← **Private** ← בלי לסמן אף תיבה ← **Create repository**.
2. מעלים לשם את **התוכן של התיקייה הזו** (ה-repo מתחיל כאן, לא תיקייה אחת מעל).

### 2. בוט טלגרם
1. בטלגרם: **@BotFather** (וי כחול) ← **Start** ← `/newbot` ← שם ← שם משתמש שמסתיים ב-`bot`.
2. שומרים את ה**טוקן**.
3. פותחים את הבוט החדש ← **Start** ← שולחים `שלום`.

### 3. מפתחות API (כולם חינמיים, בלי כרטיס אשראי)
| שירות | איפה | מה עושים |
|---|---|---|
| Finnhub | finnhub.io | **Get free API key** ← המפתח מופיע ב-Dashboard |
| Tiingo | tiingo.com | **Sign Up** ← **Account** ← **API** ← **Token** |
| FRED | fredaccount.stlouisfed.org | חשבון ← **API Keys** ← **Request API Key** |
| CoinGecko | coingecko.com/en/api/pricing | **Demo** ← **Create Free Account** ← **Developer Dashboard** ← **Add New Key** |
| Gemini | aistudio.google.com | **Get API key** ← **Create API key** |

### 4. Cloudflare, בשביל הדשבורד (חינמי)
1. dash.cloudflare.com ← **Sign up**.
2. בתפריט: **Storage & Databases** ← **KV** ← **Create** ← שם: `newsroom-data`. מעתיקים את ה-**ID**.
3. **Account ID**: בעמוד הבית של החשבון, בצד, **Account ID** ← מעתיקים.
4. ליצירת טוקן: לוחצים על אייקון הפרופיל ← **API Tokens** ← **Create Token** ← **Create Custom Token**.
   הרשאות: **Account · Workers KV Storage · Edit** ו-**Account · Workers Scripts · Edit** ← **Create**.

### 5. Secrets ב-GitHub
ב-repo: **Settings** ← **Secrets and variables** ← **Actions** ← **New repository secret**:

| שם | ערך |
|---|---|
| `TELEGRAM_BOT_TOKEN` | מ-BotFather |
| `TELEGRAM_CHAT_ID` | בשלב 6 |
| `FINNHUB_API_KEY`, `TIINGO_API_KEY`, `FRED_API_KEY`, `COINGECKO_API_KEY`, `GEMINI_API_KEY` | מהשלב הקודם |
| `SEC_CONTACT` | האימייל שלך (SEC דורשת אותו) |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID` | מ-Cloudflare |
| `DASHBOARD_KEY` | אופציונלי: מילה סודית. אז הדשבורד נפתח רק בכתובת `...?k=המילה` (פעם אחת, ואחר כך נזכר) |
| `HEALTHCHECK_URL` | אופציונלי, שלב 8 |

### 6. chat_id
**Actions** ← **newsroom** ← **Run workflow** ← `task: whoami` ← פותחים את ההרצה ← שלב **Run** ← שורה `chat_id = ...` ← שומרים כסוד `TELEGRAM_CHAT_ID`.

### 7. בדיקה והפעלה
1. **Run workflow** עם `probe`: רשימת ✅/❌ לכל מקור, בטלגרם.
2. **Actions** ← **dashboard** ← **Run workflow**: פורס את הדשבורד. הכתובת מופיעה בלוג (`https://newsroom.<שם>.workers.dev`).
   מעתיקים אותה ל-`dashboard_url` ב-`config/settings.yaml`.
3. **Run workflow** עם `morning`: מהדורת בוקר אמיתית עכשיו. אפשר גם `preopen`, `close`, `weekly`.
4. בטלפון: פותחים את הדשבורד ← **שיתוף** ← **הוסף למסך הבית**.

### 8. לפני הנסיעה (מומלץ): התראה אם GitHub מפסיק להריץ
healthchecks.io ← **Sign Up** ← **Add Check** (Period: 1 hour, Grace: 2 hours) ← **Integrations** ← **Telegram** ← מעתיקים את כתובת ה-Ping לסוד `HEALTHCHECK_URL`.

---

## ⚙️ שינוי הגדרות

| מה | איפה |
|---|---|
| רשימת המעקב | בבוט: `/add`, `/remove`, `/list`, או `config/watchlist.yaml` |
| רגישות התראות: ציון מינימלי, דחוף, צינון, תקרה יומית | `config/settings.yaml` ← `alerts` |
| "תנועה חריגה" (ברירת מחדל 2 סטיות תקן) | `config/settings.yaml` ← `volatility.alert_sigma` |
| ספי השוק כולו (S&P, נאסד"ק, ביטקוין, נפט, VIX, אג"ח) | `config/market.yaml` ← `market_alerts` |
| שעות שקט | `config/settings.yaml` ← `quiet_hours` |
| שעות המהדורות | `config/settings.yaml` ← `editions` |
| ספק ומודל שפה | `config/settings.yaml` ← `llm` (המודלים נוסים לפי הסדר) |
| כללי "שרשרת ההשפעה", משקלות סקטורים, מילות מפתח | `config/market.yaml` |
| מועדי הפד ל-2027 | `config/market.yaml` ← `fomc_decisions`. **לאמת ולהוסיף לפני ינואר.** |

**פקודות הבוט:** `/add` · `/remove` · `/list` · `/settings` · `/pause` (גם `/pause 6h`, `/pause 2d`) · `/resume` · `/help`.
בזמן השהיה ההתראות נאספות ומופיעות במהדורה הבאה. המהדורות עצמן ממשיכות.

---

## 🧯 כשמשהו נשבר

| מה רואים | מה עושים |
|---|---|
| "⚠️ מקורות שלא ענו: X" | בדרך כלל זמני. אם חוזר כמה ימים: `probe`. |
| "⚙️ מהדורת גיבוי" | `probe` ← השורה "Gemini models". אם מודל הוצא משימוש, מחליפים ב-`llm.models`. |
| "X משפטים נפסלו בבדיקת המספרים" | תקין. המודל כתב מספר שלא היה בנתונים, והמשפט נמחק. |
| "⚠️ המערכת נתקלה בתקלה · <חלק>" | **Actions** ← ההרצה האחרונה ← הלוג. ההרצה הבאה תנסה שוב בעצמה. |
| הדשבורד לא מתעדכן | לבדוק את סודות Cloudflare. הנתונים נכתבים ל-KV בכל הרצה. |
| לא מגיע כלום בכלל | **Actions**: יש הרצות? אם לא: **newsroom** ← **Enable workflow**. |

---

## 💰 תקציב (₪0)
- **GitHub Actions** (repo פרטי, 2,000 דקות בחודש): כ-1,365 הרצות. כל אחת חייבת להישאר מתחת לדקה. ברירת המחדל של מגבלת ההוצאה היא $0, כלומר **אין חיוב**. בחריגה ההרצות פשוט נעצרות. ב-repo ציבורי הדקות לא מוגבלות.
- **הדשבורד:** המעטפת נפרסת רק כשהקוד שלה משתנה. בכל הרצה נשלח לשירות האחסון (KV) קובץ נתונים קטן אחד, בקריאה אחת (המכסה: 1,000 כתיבות ביום).
- **Gemini:** קריאה אחת למהדורה. בהתראות, קריאה רק כשיש מועמדים. אצווה אחת לכל ההתראות.
- **Finnhub:** עד 55 קריאות לדקה, עם מגביל קצב מובנה.

## 🔐 פרטיות
רק סימולים, בלי סכומים. כל המפתחות ב-Secrets, והקוד מוחק אותם מכל הודעת שגיאה. אפשר לנעול את הדשבורד עם `DASHBOARD_KEY`.

---

## 💻 למפתחים

```bash
pip install -r requirements.txt
python -m pytest -q
```

```bash
PYTHONPATH=src python -m newsroom.tools.demo
```

```bash
python -m http.server -d dashboard/public 8000
```

הפקודה השנייה מייצרת נתוני הדגמה לדשבורד, עם באנר בולט "נתוני הדגמה". השלישית מגישה את הדשבורד מקומית, בכתובת http://localhost:8000.

```
src/newsroom/
  main.py            הפעימה: כל חלק רץ בנפרד, וכשל של אחד לא עוצר את האחרים
  scheduler.py       שעות, חגי NYSE, ימים מקוצרים, "מה מגיע עכשיו"
  snapshot.py        שכבת איסוף אחת לכולם
  collectors/        מקור לכל קובץ
  processing/        תנודתיות, קיבוץ, ציון חשיבות, מזג אוויר, MAGS
  alerts/            זיהוי, נגד רעש, ניסוח, מאקרו
  editions/          בוקר, לפני הפתיחה, סגירה, שבועי
  llm/               ספק, Gemini, בודק מספרים, הנחיות כתיבה
  site/build.py      data.json לדשבורד + העלאה ל-KV
  telegram/          שליחה ובוט
dashboard/
  public/            הדשבורד: HTML/CSS/JS בלי ספריות, PWA
  src/worker.js      Cloudflare Worker: מגיש קבצים + data.json, נעילה אופציונלית
tests/               85 בדיקות
```
