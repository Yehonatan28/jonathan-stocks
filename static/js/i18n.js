/* Jonathan Stocks · English / Hebrew
   The language is chosen in the Display menu and stored in this browser. Hebrew sets lang="he" and
   dir="rtl" on the page, so the layout mirrors (the sidebar moves right, reading order flips) while
   numbers, symbols and prices stay left-to-right inside their cells.
   Scope, stated plainly: the shell (navigation, page headers, top bar, search, display menu,
   sign-in), the home screen and shared states are translated. Tables, forms and method notes inside
   the tools are still English; financial terms keep their English names next to the Hebrew, as in
   the glossary. One dictionary, so a term is translated the same way everywhere it appears. */
(function () {
  'use strict';
  const HE = {
    // areas and tabs
    'Market': 'שוק', 'Research': 'מחקר', 'Portfolio': 'תיק', 'Lab': 'מעבדה',
    'Overview': 'סקירה', 'Heatmap': 'מפת חום', 'News': 'חדשות', 'Calendar': 'יומן',
    'Company': 'חברה', 'Screener': 'סורק', 'Compare': 'השוואה', 'Trend view': 'מגמות', 'Assistant': 'עוזר מחקר',
    'Holdings': 'החזקות', 'Transactions': 'עסקאות', 'Watchlist': 'רשימת מעקב', 'Daily check': 'בדיקה יומית', 'Risk': 'סיכון', 'Alerts': 'התראות',
    'Strategy Lab': 'מעבדת אסטרטגיות', 'Engine replay': 'הרצה היסטורית', 'Gaps': 'פערי פתיחה',
    // page titles
    'Market overview': 'סקירת שוק', 'Market heatmap': 'מפת חום של השוק', 'Market news': 'חדשות שוק',
    'Company research': 'מחקר חברה', 'Stock screener': 'סורק מניות', 'Compare & correlate': 'השוואה ומתאם',
    'Trend comparison': 'השוואת מגמות', 'Research assistant': 'עוזר מחקר', 'Transactions & P&L': 'עסקאות ורווח והפסד',
    'Portfolio risk': 'סיכון התיק', 'Engine replay ': 'הרצה היסטורית', 'Gap detection': 'זיהוי פערי פתיחה',
    // benefit sentences
    'What moved today, how broad the move was, and what to look at next.': 'מה זז היום, כמה רחבה הייתה התנועה, ומה כדאי לבדוק עכשיו.',
    'Every S&P 500 member by sector, sized by market value and coloured by today’s change.': 'כל חברות S&P 500 לפי סקטור: גודל לפי שווי שוק, צבע לפי השינוי היום.',
    'Headlines from US and Israeli publishers, deduplicated, with a feed per symbol.': 'כותרות ממקורות בארה״ב ובישראל, בלי כפילויות, עם עדכון לכל סימול.',
    'Earnings, economic releases and dividends for the next two weeks; your names are marked.': 'דוחות, נתוני מאקרו ודיבידנדים לשבועיים הקרובים; המניות שלך מסומנות.',
    'Statements as filed with the SEC, five years and eight quarters, every ratio with its formula.': 'דוחות כפי שהוגשו ל־SEC: חמש שנים ושמונה רבעונים, כל יחס עם הנוסחה שלו.',
    'Filter the S&P 500 and Nasdaq-100; each filter shows how many names have the field.': 'סינון S&P 500 ו־Nasdaq-100; כל מסנן מראה לכמה מניות יש את הנתון.',
    'Up to eight symbols on the same days: return from 100, risk, drawdown, beta and correlation.': 'עד שמונה סימולים על אותם ימים: תשואה מ־100, סיכון, ירידה משיא, בטא ומתאם.',
    'Two symbols side by side on the trend engine’s daily reading.': 'שני סימולים זה לצד זה לפי קריאת המגמה היומית.',
    'Questions answered only from this site’s data, with sources, and every number checked.': 'תשובות רק מנתוני האתר, עם מקורות, וכל מספר נבדק.',
    'Your open positions with stops, value and profit at delayed prices.': 'הפוזיציות הפתוחות שלך עם סטופ, שווי ורווח, במחירים מושהים.',
    'Buys, sells, dividends and splits; cost and gains first-in, first-out, per currency.': 'קניות, מכירות, דיבידנדים ופיצולים; עלות ורווח לפי FIFO, לכל מטבע בנפרד.',
    'Names you follow; the daily check scans them for technical setups.': 'מניות שאתה עוקב אחריהן; הבדיקה היומית סורקת אותן לתבניות טכניות.',
    'Your stop and exit rules evaluated on the last daily close, with what was and was not checked.': 'כללי הסטופ והיציאה שלך על סגירת היום האחרונה, כולל מה נבדק ומה לא.',
    'Exposure and limit breaches first: weights, open risk to stops, sectors and correlation.': 'חשיפה וחריגות מהמגבלות קודם: משקלים, סיכון עד הסטופ, סקטורים ומתאם.',
    'Rules on price, RSI, averages, volume and earnings. Checked only while this site is open.': 'כללים על מחיר, RSI, ממוצעים, מחזור ודוחות. נבדקים רק כשהאתר פתוח.',
    'Your entry and exit rules on daily history against buy and hold, with costs and next-open fills.': 'כללי הכניסה והיציאה שלך על היסטוריה יומית מול קנה והחזק, עם עלויות וביצוע בפתיחה הבאה.',
    'The daily check’s own rules replayed on one symbol’s history.': 'כללי הבדיקה היומית מורצים על ההיסטוריה של סימול אחד.',
    'Overnight gaps measured in ATR, and whether the day filled them.': 'פערי פתיחה נמדדים ביחידות ATR, והאם היום סגר אותם.',
    // primary actions
    'Search a company': 'חיפוש חברה', 'Find a company': 'מציאת חברה', 'Save this screen': 'שמירת הסינון', 'Add symbols': 'הוספת סימולים',
    'Choose symbols': 'בחירת סימולים', 'Ask a question': 'שאלת שאלה', 'Add a position': 'הוספת פוזיציה', 'Record a transaction': 'רישום עסקה',
    'Add a symbol': 'הוספת סימול', 'Run the check again': 'הרצת הבדיקה מחדש', 'Size a position': 'חישוב גודל פוזיציה', 'Create an alert': 'יצירת התראה',
    'Run the backtest': 'הרצת הבדיקה', 'Choose a symbol': 'בחירת סימול',
    // top bar and menus
    'Search company or symbol': 'חיפוש חברה או סימול', 'Glossary': 'מילון מונחים', 'Sign in': 'כניסה', 'Sign out': 'יציאה',
    'Display': 'תצוגה', 'Theme': 'ערכת צבעים', 'Dark': 'כהה', 'Light': 'בהירה', 'Match the system': 'לפי המערכת',
    'Density': 'צפיפות', 'Comfortable': 'נוחה', 'Compact': 'דחוסה', 'Language': 'שפה',
    'Pause': 'השהיה', 'Play': 'הפעלה', 'Hide': 'הסתרה', 'Show tape': 'הצגת הסרט', 'Skip to content': 'דילוג לתוכן',
    'US market open': 'המסחר בארה״ב פתוח', 'US market closed': 'המסחר בארה״ב סגור',
    // search
    'Company or symbol, e.g. Microsoft or MSFT': 'חברה או סימול, למשל Microsoft או MSFT', '↑ ↓ move · Enter opens · Esc closes': '↑ ↓ מעבר · Enter פתיחה · Esc סגירה',
    'Recent': 'אחרונים', 'Searching…': 'מחפש…',
    // home
    'Market now': 'השוק עכשיו', 'Today in brief': 'היום בקצרה', 'Your names today': 'המניות שלך היום',
    'Descriptions of today’s data, not forecasts. Open “Basis” for the numbers.': 'תיאור של נתוני היום, לא תחזית. ב״בסיס״ מופיעים המספרים.',
    'Basis': 'בסיס', 'Breadth': 'רוחב השוק', 'Sectors': 'סקטורים', 'Volatility': 'תנודתיות', 'Rates': 'ריביות',
    'Find a company to follow': 'מציאת חברה למעקב', 'Add a holding': 'הוספת החזקה', 'Retry': 'ניסיון חוזר',
    'Chart': 'גרף', 'Table': 'טבלה', 'Annual': 'שנתי', 'Quarterly': 'רבעוני', 'Map': 'מפה',
    'Continue as guest': 'המשך כאורח', 'Create account': 'יצירת חשבון',
    'quotes delayed, retrieved': 'מחירים מושהים, נמשכו ב־',
    'Follow a few names and this space lists what is notable about them today: large moves, unusual volume, 52-week extremes, a stop nearby, a report this week.':
      'עקבו אחרי כמה מניות, וכאן יופיע מה בולט בהן היום: תנועה גדולה, מחזור חריג, שיא או שפל של 52 שבועות, סטופ קרוב או דוח השבוע.',
  };
  const H = document.documentElement;
  const get = () => { try { return localStorage.getItem('js.lang') || 'en'; } catch (e) { return 'en'; } };
  let lang = get();
  window.T = (s) => (lang === 'he' && HE[s] ? HE[s] : s);
  window.LANG = () => lang;

  function applyStatic(root) {
    (root || document).querySelectorAll('[data-i18n]').forEach((el) => {
      const k = el.dataset.i18n;
      if (!el.dataset.en) el.dataset.en = k;
      el.textContent = lang === 'he' && HE[k] ? HE[k] : k;
    });
    (root || document).querySelectorAll('[data-i18n-ph]').forEach((el) => {
      const k = el.dataset.i18nPh; el.placeholder = lang === 'he' && HE[k] ? HE[k] : k;
    });
  }
  function apply() {
    H.lang = lang === 'he' ? 'he' : 'en';
    H.dir = lang === 'he' ? 'rtl' : 'ltr';
    applyStatic();
  }
  apply();
  document.addEventListener('DOMContentLoaded', () => applyStatic());
  window.setLang = (l) => {
    lang = l === 'he' ? 'he' : 'en';
    try { localStorage.setItem('js.lang', lang); } catch (e) { /* this visit only */ }
    apply();
    document.dispatchEvent(new CustomEvent('langchange'));
  };
  window.i18nApply = applyStatic;
})();
