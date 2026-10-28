# Jonathan Stocks · Trading Terminal

A personal trading terminal: portfolio risk management, technical signals,
backtesting, a sector heatmap and market data. The interface is in English;
the glossary keeps its Hebrew explanations under English terms.

> **Your positions are private.** Every stored row is scoped to your account,
> and `test_security.py` proves it: a second signed-in user sees an empty
> portfolio, cannot read your settings, and cannot read, edit or delete your
> positions by guessing their id. Anonymous requests to those routes are
> rejected outright.

---

## Command centre (🎯)

The heart of the system. On every load it scans your positions and watchlist
and produces a plan.

### 1. What to do now
Actions are ranked by severity, worst first:

| Code | Fires when | Severity |
|---|---|---|
| `STOP_HIT` | Price fell below the stop you set | Critical |
| `SET_STOP` | A position has no stop at all | Urgent |
| `STOP_NEAR` | Less than 2% left to the stop | Urgent |
| `BREAKEVEN` | Profit passed 1R — the risk can be removed | Urgent |
| `TREND_BREAK` | Price closed under the 50-day and the trend broke | Urgent |
| `TRAIL_UP` | The trailing stop has risen — lock in more | Review |
| `TAKE_PARTIAL` | Over 3R with a stretched RSI | Review |
| `RISK_OVERSIZE` | Position risk exceeds your policy | Review |
| `PORTFOLIO_HEAT` | Total open risk passed 8% of the account | Urgent |

Each carries a one-click **Set stop $X** and a **Mark done** that hides it for
the day once the order is live with your broker.

### 2. Positions
Edit stops inline, switch between **fixed** and **trailing**, and read:
**Distance** to the stop, **R** (profit in units of the risk taken), **Risk $**,
and the level the engine currently suggests.

### 3. Entry opportunities
Scanned from the watchlist only. Each signal carries an entry zone, a stop, two
targets and a share count sized to your risk policy.

---

## Heatmap (🗺)

A squarified treemap of the **full S&P 500 (507 names) or the Nasdaq 100**:
block size is market cap, colour is today's move, blocks are grouped by sector.
Hovering a block gives price, today's change, market cap, sector — and the
**pre-market or after-hours print with its own percentage**, kept as a separate
row because an extended-hours move is measured against the last regular close,
not folded into the day's change. A name with no extended-hours print simply
has no row; nothing is invented to fill it.

Quotes come from Yahoo's batch endpoints — 500 names cannot each have their own
request — with a crumb-authenticated call first, the spark endpoint next, and
per-ticker only for whatever those miss. Market caps are taken live where the
feed provides them, falling back to a stored estimate.

Squarified rather than slice-and-dice because slivers cannot be read or
clicked. What a block draws depends on what fits: large blocks get logo, symbol,
company name and percentage; small ones fall back to the **company logo**, which
still identifies the company where no label would fit. A logo that fails to load
is removed and the symbol shows instead, so a block is never blank.

---

## Gap detector (⚡)

A gap is the distance between today's open and yesterday's close — price that
never traded. The scanner reports every gap above a threshold across the
largest S&P names or your own, and ranks them by size.

What it shows beyond the percentage:

- **Filled or unfilled.** An unfilled gap leaves an untested level behind; a
  filled one has already been rejected intraday. The bar on each row is how
  much of the gap price has taken back.
- **Size in ATR**, because 2% is routine in one stock and a shock in another.
- **Held or faded** — whether the close stayed on the gap's side of the open.
- Volume relative to the 20-day average, and the exact price that fills it.

## Fear & Greed (CNN)

Read from the same JSON CNN's own page uses, with the dial, needle, rating,
previous close/week/month/year and all seven component indicators. When CNN
cannot be reached the panel says so — **a sentiment number invented locally
would be worse than an empty panel.**

---

## Backtest (🧪)

Replays **exactly the rules the command centre gives you today** over the
stock's history. `analyze()` and `backtest()` share one `_snapshot()` builder,
so the test exercises the live rules rather than a second implementation.

**No lookahead:** a signal at a close is entered at the next session's open, and
every stop decision uses only bars up to that point. There is a test for this —
appending future bars must not change a single trade that already closed.

Reports trades, win rate, expectancy in R, worst trade and exposure against
buy-and-hold, including each one's maximum drawdown. The drawdown comparison is
usually the interesting one: that is where stops earn their keep.

---

## Charts

Candles, line or area; **MA50 / MA100 / MA150 / MA200**; Bollinger bands;
volume; RSI and MACD panes; log scale; fullscreen. A crosshair legend tracks the cursor with OHLC,
change, volume and the moving averages under it.

The chart also draws what the system is telling you to do: suggested and
trailing stops, entry zone and targets, your own entry and stop when the name is
held, and the backtest's fills.

---

## News (📰)

RSS rather than Yahoo's search endpoint, which rate-limits and answers with an
empty list instead of an error. Sources: CNBC, MarketWatch, Investing.com,
Yahoo Finance, FT, plus Globes, Calcalist, TheMarker and Bizportal — a portfolio
holding TASE names is barely covered in the English press.

Every feed is fetched independently and a failure is returned rather than
raised, so one dead outlet cannot empty the page; the UI names the quiet ones.
`GET /api/news/sources` reports which feeds actually answer from your
deployment.

### Every headline gets a picture

Where a feed carries real article art it is used: Media RSS thumbnails (widest
wins), `media:content`, enclosures, channel images, and the first usable `<img>`
in the description — tracking pixels and sub-120px images rejected.

Most wire stories carry none, so the rest are **drawn from what the story is
about** rather than filled with a decorative stock photo. `classify()` reads the
headline for three things — topic (rates, inflation, jobs, energy, crypto,
semis, AI, M&A, earnings, policy, housing, health, or markets), direction from
the verb, and the company, matched by symbol or by name since "Nvidia beats"
never contains NVDA — and the browser draws from that: policy stories get a
stepped rate curve, earnings get bars, semis get circuit traces, energy gets
flow bands, and anything else gets candles. Direction tints the accent green or
red, the caption names the topic and the company, and the motif's weight and
detail follow the size of the box, so a 96px thumbnail and the hero panel are
each drawn for their own shape.

The classification is returned as data and tested without a browser; the drawing
lives in the UI. A real photo is layered over the art, so a photo that never
loads leaves the drawing rather than a broken image.

---

## How the stops are calculated

The regime also checks the **trend template** — the 50-day above the 150-day
above the 200-day — which is a stronger statement about trend health than the
50/200 golden cross alone.

**Initial stop** — the lower of a structural level (the 10-day swing low less a
quarter ATR) and a volatility level (price less 2×ATR), capped at 3.5×ATR of
risk and floored at 0.8×ATR so it does not sit inside the noise.

**Trailing stop** (Chandelier Exit) — the 22-day high less 2.5–3×ATR by trend
strength. It **only ever rises**.

**Position size** — `(account × risk%) ÷ (entry − stop)`, capped at a third of
the account in one name.

---

## Security

| Concern | How it is handled |
|---|---|
| Account isolation | Every query scoped by `user_id`; verified by test |
| Password storage | PBKDF2-HMAC-SHA256, per-user salt, 240k rounds; legacy hashes upgrade silently on next sign-in |
| Session cookies | HttpOnly, SameSite=Lax, Secure on any real deployment |
| Brute force | Failed sign-ins throttled per source address |
| Session key | Never a checked-in constant — set `SECRET_KEY` in the environment |

---

## Running locally

```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

## Hosting

Signed-in users are stored in SQLite on the server. Guest mode keeps everything
in the browser. Both drive the same engine.

**Render** — `render.yaml` targets the free plan, no card needed:
`New` → `Blueprint` → pick the repo → `Apply`. The free plan has a writable
filesystem so accounts work, but the container is rebuilt on each deploy and
after it sleeps, and each rebuild starts from an empty database. For durable
accounts set `plan: starter` and uncomment the `disk:` block and `DB_PATH`.

**Vercel** — `vercel.json` and `api/index.py` run Flask as a serverless
function. There is no persistent disk: the database lives in `/tmp` and is wiped
on every cold start, so **registered accounts do not survive there**. Guest mode
is unaffected.

### Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs session cookies. Required in production — without it a random key is generated and every restart signs everyone out |
| `DB_PATH` | Where the SQLite file lives. On Render point it at the persistent disk |

---

## Tests

```bash
python3 test_engine.py      # indicators, regimes, stops, setups, backtest  (no network)
python3 test_news.py        # RSS/Atom parsing against sample feeds         (no network)
python3 test_security.py    # account isolation, hashing, cookies           (no network)

python3 devserver.py &      # the app with every upstream stubbed
node test_ui.js             # language, gauge, heatmap geometry, chart
node test_flows.js          # portfolio, command centre, backtest, news, guest mode
```

Every upstream the app uses is blocked from the sandbox this was built in, so
the suites stub them and exercise the logic instead. The browser tests stub the
charting library and assert on what the chart asks to draw.

---

## Layout

| File | Role |
|---|---|
| `engine.py` | Indicators, regime, setups, stop management, portfolio risk, backtest |
| `market.py` | Index constituents with sector and market cap; CNN Fear & Greed |
| `news.py` | RSS sources, resilient fetch, parsing, merge |
| `app.py` | Flask: auth, portfolio, watchlist, alerts, market data, engine routes |
| `templates/index.html` | The entire interface |
| `devserver.py` | Local run with stubbed upstreams, for the browser tests |

### Engine API

- `GET /api/engine/analyze/<ticker>` — full technical picture
- `POST /api/engine/plan` — the action plan. Signed in: read from the database. Guest: posted in the body
- `GET /api/engine/backtest/<ticker>?years=3` — the rules replayed over history
- `GET /api/chart/<ticker>?period=6mo` — candles plus moving averages, RSI and MACD
- `GET /api/heatmap/<index>` — constituents with sector, cap and change
- `GET /api/gaps?scope=sp100|mine&min=1` — opening gaps, largest first
- `GET /api/feargreed` — CNN's index
- `GET /api/news?scope=all|us|il|mine` — headlines
- `GET /api/news/sources` — which feeds are alive from this deployment
- `PATCH /api/portfolio/<id>` — stop, stop type, target, quantity
- `GET|POST /api/settings` — risk policy

---

## Design

A dark terminal: layered surfaces and 1px borders instead of blur, tabular
figures so number columns align, and colour reserved for facts about money.
Nothing depends on colour alone — severities carry a word, price moves carry an
arrow — and every text-on-surface pair meets WCAG AA.

---

> This is an analysis and trading-discipline tool, not investment advice.
> Prices come from Yahoo Finance and news from RSS feeds; both can lag.
