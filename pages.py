"""Public pages: about, privacy, terms, disclaimer and methodology.

The methodology page is assembled from the same method texts each module shows on its own
screen, so the published explanation cannot drift from the code that runs.
"""
from html import escape

UPDATED = '25 November 2026'
NAV = [('/', 'Open the app'), ('/about', 'About'), ('/methodology', 'Data & methodology'),
       ('/privacy', 'Privacy'), ('/terms', 'Terms'), ('/disclaimer', 'Disclaimer')]

ABOUT = """
<div class="hero"><p class="lead">Market context, company research, portfolio accounting and risk tools in one place,
with the source and freshness of every number shown beside it.</p></div>
<div class="feat">
<div><b>Market Intelligence</b><span>Breadth over all S&amp;P 500 members, sectors against the index, rates, currencies and commodities.</span></div>
<div><b>Equity Research</b><span>Five years of statements from SEC filings, a stock screener, and side-by-side comparison with correlation.</span></div>
<div><b>Portfolio</b><span>Transactions with first-in, first-out lots, realised and unrealised gains, and time-weighted performance against the S&amp;P 500.</span></div>
<div><b>Quant &amp; Risk</b><span>Risk against your own limits, position sizing, a strategy backtester without look-ahead, and gap detection.</span></div>
</div>
<h2>Principles</h2>
<ul>
<li><strong>Provenance on every screen.</strong> Each dataset carries its source, whether it is delayed, end-of-day or as filed, and when it was retrieved.</li>
<li><strong>No invented numbers.</strong> A figure whose inputs are missing is shown as a dash, never estimated or filled with zero. Statistics that need history (Sharpe, beta, annualised return) appear only once there is enough of it.</li>
<li><strong>Information, not advice.</strong> There are no buy or sell calls. The tools describe trends, risk and history; decisions are yours.</li>
<li><strong>Privacy by default.</strong> Guest mode: your entries are saved in this browser; sent to the server only to compute results, and not stored there. Accounts store only what you enter, and you can delete the account and all of it at any time.</li>
</ul>
<h2>How it is built</h2>
<p>A Python (Flask) service with a dependency-free JavaScript interface, deployed on Vercel with a Turso (libSQL) database.
Market data comes from Yahoo Finance's public endpoints, company financials from SEC EDGAR, sentiment from CNN's Fear &amp; Greed index,
and news from publishers' RSS feeds. Every calculation (indicators, ledger, performance, risk, backtests) is covered by automated tests
checked against hand calculations. See <a href="/methodology">Data &amp; methodology</a> for each method in full.</p>
"""

PRIVACY = """
<p class="doc-note">Short version: no advertising, no analytics, no tracking cookies. Guest mode: your entries are saved in this browser; sent to the server only to compute results, and not stored there.
An account stores what you enter and nothing else, and you can delete it with everything in it.</p>
<h2>What is stored, and where</h2>
<table><thead><tr><th>Data</th><th>Where</th><th>Why</th></tr></thead><tbody>
<tr><td>Username, email and a password hash (PBKDF2, never the password itself)</td><td>The service's database (Turso)</td><td>To sign you in</td></tr>
<tr><td>Holdings, transactions, watchlist, alerts and risk settings you enter</td><td>The service's database, under your account only</td><td>To show them to you</td></tr>
<tr><td>A signed session cookie (HttpOnly, Secure, SameSite=Lax)</td><td>Your browser</td><td>To keep you signed in for up to 30 days</td></tr>
<tr><td>Guest data, screens you saved, preferences</td><td>Your browser's local storage</td><td>Nothing of it is stored on the server</td></tr>
<tr><td>Failed sign-in attempts: a keyed hash of the address, never the address</td><td>The service's database, deleted after 24 hours</td><td>To slow down password guessing</td></tr>
</tbody></table>
<h2>Calculations in guest mode</h2>
<p>To compute a guest's ledger, performance or risk, the browser sends the transactions or holdings to the server. They are computed in
memory and returned; they are not written to the database or to logs by this service.</p>
<h2>Third parties</h2>
<ul>
<li><strong>Hosting:</strong> Vercel runs the service and, like any host, records technical request logs (address, time, path).</li>
<li><strong>Database:</strong> Turso stores the account data listed above.</li>
<li><strong>Market and company data:</strong> the server, not your browser, asks Yahoo Finance, SEC EDGAR, CNN and news publishers. No personal data is included in those requests.</li>
<li><strong>Fonts:</strong> the Hebrew typeface is loaded from Google Fonts, which receives your browser's address when it does. All other fonts are served by this site.</li>
<li><strong>News images</strong> load from the publishers' own servers when you open the news screen.</li>
<li><strong>Research assistant:</strong> a question you ask there is sent to Google (Gemini) with the market and company data
needed to answer it. Your holdings are added only if you tick the consent box for that question. Google's terms for the Gemini
API apply to what is sent. Do not type personal information into questions.</li>
</ul>
<p>There is no advertising, no analytics service and no sale of data. Data leaves the service only as listed above.</p>
<h2>Your choices</h2>
<ul>
<li>Use guest mode: your entries are saved in this browser; sent to the server only to compute results, and not stored there.</li>
<li>Delete your account below: your holdings, transactions, watchlist, alerts, settings and the account itself are erased immediately.</li>
<li>Clear guest data by clearing this site's data in your browser.</li>
</ul>
<h2 id="delete">Delete your account</h2>
<div class="doc-note doc-danger"><p>This permanently erases the account and everything stored under it. It cannot be undone.</p>
<form id="delForm"><input type="password" id="delPass" placeholder="Your password" autocomplete="current-password" required aria-label="Your password">
<button class="btn btn-sm" type="submit" style="background:var(--dn);color:#fff">Delete my account</button><span id="delMsg" role="status"></span></form></div>
<script src="/static/js/account.js"></script>
"""

TERMS = """
<h2>What this is</h2>
<p>Jonathan Stocks is a personal portfolio project offered free of charge, as it is. It provides market information and analysis tools.
It is not a broker, does not execute trades, does not hold money, and is not a licensed investment adviser.</p>
<h2>No advice</h2>
<p>Nothing on the site is a recommendation to buy, sell or hold any security, or a statement that an investment suits you.
Trend states, risk findings, screens and backtests describe data and history under stated assumptions. See the <a href="/disclaimer">disclaimer</a>.</p>
<h2>Data</h2>
<p>Market data is delayed or end-of-day and comes from third parties that may be late, incomplete or wrong, and may stop being available.
Company figures are taken from SEC filings as reported. Every screen shows where its data comes from and when it was retrieved; check
anything that matters against an official source before relying on it.</p>
<h2>Your account</h2>
<p>Keep your password to yourself. You are responsible for what you enter. You may delete your account at any time from the
<a href="/privacy#delete">privacy page</a>.</p>
<h2>Fair use</h2>
<p>Do not try to break, overload or scrape the service, or to reach other users' data. Requests are rate-limited.</p>
<h2>No warranty, limited liability</h2>
<p>The service is provided without any warranty. To the extent the law allows, its author is not liable for losses arising from its use,
from decisions made with it, or from errors or interruptions in the data.</p>
<h2>Changes</h2>
<p>These terms and the service may change or end. The date at the top shows the latest revision.</p>
"""

DISCLAIMER = """
<p class="doc-note"><strong>Information only, not investment advice.</strong> Jonathan Stocks is not a broker, dealer or licensed investment
adviser, and nothing on it is an offer, a solicitation or a personal recommendation.</p>
<ul>
<li><strong>Delayed data.</strong> Quotes may lag the exchange by 15 minutes or more; analysis uses end-of-day bars. Nothing here is a real-time feed.</li>
<li><strong>Past results.</strong> Backtests and performance figures describe the past under stated assumptions (fills at the next open, costs as entered,
no look-ahead). They do not predict future results. Real trading has gaps, partial fills and taxes the model may not capture.</li>
<li><strong>Stops are not guarantees.</strong> A price can gap past a stop, so a loss can be larger than the risk calculated to it.</li>
<li><strong>Estimates are labelled.</strong> Forward valuation figures are consensus estimates, not results, and are marked as such.</li>
<li><strong>Your decisions.</strong> You are responsible for your investment decisions. Consider your circumstances and, where appropriate,
a licensed professional.</li>
</ul>
"""


def methodology(sources, sections):
    """sources: provenance catalogue; sections: [(title, method text)]."""
    rows = ''.join(f"<tr><td>{escape(d['label'])}</td><td>{escape(d['source'])}</td><td>{escape(d['meaning'])}</td></tr>" for d in sources)
    out = [
        '<p class="doc-note">Every screen links back to its method. The texts below are the same ones the screens show, taken from the code that runs.</p>',
        '<h2>Data sources</h2>',
        f'<table><thead><tr><th>Dataset</th><th>Source</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>',
        '<p>Each data answer carries <code>X-Data-Source</code>, <code>X-Data-Status</code> and <code>X-Data-Retrieved</code> headers; '
        'the badge at the top of each screen shows them. A cached answer reports the time of the original retrieval.</p>',
        '<h2>Indicators</h2>',
        '<p>One library computes every indicator on every screen: simple and exponential moving averages, RSI(14) and ATR(14) with '
        "Wilder's smoothing (seeded with the simple average of the first 14 values), MACD 12/26/9, ADX, Bollinger Bands (population "
        'standard deviation), OBV, VWAP and the stochastic oscillator. All are causal: a value at a bar uses that bar and earlier ones only. '
        'Tests check RSI and ATR against hand calculations and against a loop implementation, and check that no future bar changes a past value.</p>',
    ]
    for title, text in sections:
        out.append(f'<h2>{escape(title)}</h2><pre>{escape(text.strip())}</pre>')
    return ''.join(out)


def page(title, body, path, description, updated=True):
    return {'title': title, 'body': body, 'path': path, 'description': description, 'nav': NAV,
            'updated': UPDATED if updated else None}
