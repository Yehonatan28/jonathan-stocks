"""Market-wide data: index constituents and CNN's Fear & Greed index.

Two things the app needs that are not per-ticker technicals:

  * a constituent table with sector, market cap and company domain, which is
    what a sector treemap needs and what the quote API does not provide;
  * CNN's published Fear & Greed index, read from the same JSON its own page
    reads, rather than a number invented locally from whatever breadth the
    app happened to scan.
"""

import time

import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
}

_CACHE = {}


def _cached(key, ttl, build):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    value = build()
    _CACHE[key] = (time.time() + ttl, value)
    return value


# ------------------------------------------------- 1. index constituents ---
# (ticker, company, sector, market cap in $B, domain for the logo)
# Market caps are approximate and used only for relative block sizing, which
# is all a treemap needs; the domain drives the logo lookup.
SP500 = [
    ('NVDA', 'NVIDIA', 'Technology', 4400, 'nvidia.com'),
    ('MSFT', 'Microsoft', 'Technology', 3800, 'microsoft.com'),
    ('AAPL', 'Apple', 'Technology', 3300, 'apple.com'),
    ('GOOGL', 'Alphabet', 'Communication Services', 2400, 'abc.xyz'),
    ('AMZN', 'Amazon', 'Consumer Discretionary', 2300, 'amazon.com'),
    ('META', 'Meta Platforms', 'Communication Services', 1800, 'meta.com'),
    ('AVGO', 'Broadcom', 'Technology', 1300, 'broadcom.com'),
    ('TSLA', 'Tesla', 'Consumer Discretionary', 1100, 'tesla.com'),
    ('BRK-B', 'Berkshire Hathaway', 'Financials', 1050, 'berkshirehathaway.com'),
    ('JPM', 'JPMorgan Chase', 'Financials', 800, 'jpmorganchase.com'),
    ('WMT', 'Walmart', 'Consumer Staples', 780, 'walmart.com'),
    ('LLY', 'Eli Lilly', 'Health Care', 730, 'lilly.com'),
    ('ORCL', 'Oracle', 'Technology', 650, 'oracle.com'),
    ('V', 'Visa', 'Financials', 640, 'visa.com'),
    ('MA', 'Mastercard', 'Financials', 530, 'mastercard.com'),
    ('NFLX', 'Netflix', 'Communication Services', 520, 'netflix.com'),
    ('XOM', 'Exxon Mobil', 'Energy', 470, 'exxonmobil.com'),
    ('COST', 'Costco', 'Consumer Staples', 420, 'costco.com'),
    ('JNJ', 'Johnson & Johnson', 'Health Care', 400, 'jnj.com'),
    ('HD', 'Home Depot', 'Consumer Discretionary', 390, 'homedepot.com'),
    ('PG', 'Procter & Gamble', 'Consumer Staples', 390, 'pg.com'),
    ('PLTR', 'Palantir', 'Technology', 380, 'palantir.com'),
    ('ABBV', 'AbbVie', 'Health Care', 370, 'abbvie.com'),
    ('BAC', 'Bank of America', 'Financials', 360, 'bankofamerica.com'),
    ('CVX', 'Chevron', 'Energy', 300, 'chevron.com'),
    ('KO', 'Coca-Cola', 'Consumer Staples', 300, 'coca-colacompany.com'),
    ('GE', 'GE Aerospace', 'Industrials', 290, 'geaerospace.com'),
    ('AMD', 'AMD', 'Technology', 290, 'amd.com'),
    ('TMUS', 'T-Mobile', 'Communication Services', 280, 't-mobile.com'),
    ('CSCO', 'Cisco', 'Technology', 270, 'cisco.com'),
    ('WFC', 'Wells Fargo', 'Financials', 260, 'wellsfargo.com'),
    ('CRM', 'Salesforce', 'Technology', 260, 'salesforce.com'),
    ('PM', 'Philip Morris', 'Consumer Staples', 250, 'pmi.com'),
    ('IBM', 'IBM', 'Technology', 250, 'ibm.com'),
    ('MS', 'Morgan Stanley', 'Financials', 230, 'morganstanley.com'),
    ('UNH', 'UnitedHealth', 'Health Care', 230, 'unitedhealthgroup.com'),
    ('ABT', 'Abbott', 'Health Care', 230, 'abbott.com'),
    ('GS', 'Goldman Sachs', 'Financials', 220, 'goldmansachs.com'),
    ('LIN', 'Linde', 'Materials', 220, 'linde.com'),
    ('INTU', 'Intuit', 'Technology', 210, 'intuit.com'),
    ('MCD', "McDonald's", 'Consumer Discretionary', 210, 'mcdonalds.com'),
    ('AXP', 'American Express', 'Financials', 210, 'americanexpress.com'),
    ('DIS', 'Disney', 'Communication Services', 200, 'thewaltdisneycompany.com'),
    ('RTX', 'RTX', 'Industrials', 200, 'rtx.com'),
    ('NOW', 'ServiceNow', 'Technology', 190, 'servicenow.com'),
    ('MRK', 'Merck', 'Health Care', 190, 'merck.com'),
    ('CAT', 'Caterpillar', 'Industrials', 190, 'caterpillar.com'),
    ('T', 'AT&T', 'Communication Services', 190, 'att.com'),
    ('PEP', 'PepsiCo', 'Consumer Staples', 180, 'pepsico.com'),
    ('UBER', 'Uber', 'Industrials', 180, 'uber.com'),
    ('BKNG', 'Booking Holdings', 'Consumer Discretionary', 170, 'bookingholdings.com'),
    ('VZ', 'Verizon', 'Communication Services', 170, 'verizon.com'),
    ('TMO', 'Thermo Fisher', 'Health Care', 170, 'thermofisher.com'),
    ('SCHW', 'Charles Schwab', 'Financials', 170, 'schwab.com'),
    ('ISRG', 'Intuitive Surgical', 'Health Care', 160, 'intuitive.com'),
    ('QCOM', 'Qualcomm', 'Technology', 160, 'qualcomm.com'),
    ('BLK', 'BlackRock', 'Financials', 150, 'blackrock.com'),
    ('TXN', 'Texas Instruments', 'Technology', 150, 'ti.com'),
    ('C', 'Citigroup', 'Financials', 150, 'citigroup.com'),
    ('BA', 'Boeing', 'Industrials', 150, 'boeing.com'),
    ('SPGI', 'S&P Global', 'Financials', 150, 'spglobal.com'),
    ('AMGN', 'Amgen', 'Health Care', 140, 'amgen.com'),
    ('BSX', 'Boston Scientific', 'Health Care', 140, 'bostonscientific.com'),
    ('ADBE', 'Adobe', 'Technology', 140, 'adobe.com'),
    ('NEE', 'NextEra Energy', 'Utilities', 140, 'nexteraenergy.com'),
    ('HON', 'Honeywell', 'Industrials', 130, 'honeywell.com'),
    ('AMAT', 'Applied Materials', 'Technology', 130, 'appliedmaterials.com'),
    ('PGR', 'Progressive', 'Financials', 130, 'progressive.com'),
    ('DHR', 'Danaher', 'Health Care', 130, 'danaher.com'),
    ('GILD', 'Gilead Sciences', 'Health Care', 130, 'gilead.com'),
    ('ETN', 'Eaton', 'Industrials', 120, 'eaton.com'),
    ('PFE', 'Pfizer', 'Health Care', 120, 'pfizer.com'),
    ('COF', 'Capital One', 'Financials', 120, 'capitalone.com'),
    ('UNP', 'Union Pacific', 'Industrials', 120, 'up.com'),
    ('CMCSA', 'Comcast', 'Communication Services', 110, 'comcast.com'),
    ('MU', 'Micron', 'Technology', 110, 'micron.com'),
    ('LOW', "Lowe's", 'Consumer Discretionary', 110, 'lowes.com'),
    ('APH', 'Amphenol', 'Technology', 110, 'amphenol.com'),
    ('LRCX', 'Lam Research', 'Technology', 110, 'lamresearch.com'),
    ('ADP', 'ADP', 'Industrials', 110, 'adp.com'),
    ('ANET', 'Arista Networks', 'Technology', 100, 'arista.com'),
    ('KLAC', 'KLA', 'Technology', 100, 'kla.com'),
    ('VRTX', 'Vertex Pharma', 'Health Care', 100, 'vrtx.com'),
    ('MDT', 'Medtronic', 'Health Care', 100, 'medtronic.com'),
    ('SBUX', 'Starbucks', 'Consumer Discretionary', 100, 'starbucks.com'),
    ('PANW', 'Palo Alto Networks', 'Technology', 100, 'paloaltonetworks.com'),
    ('CRWD', 'CrowdStrike', 'Technology', 95, 'crowdstrike.com'),
    ('INTC', 'Intel', 'Technology', 95, 'intel.com'),
    ('MMC', 'Marsh McLennan', 'Financials', 90, 'marshmclennan.com'),
    ('ADI', 'Analog Devices', 'Technology', 90, 'analog.com'),
    ('CB', 'Chubb', 'Financials', 90, 'chubb.com'),
    ('LMT', 'Lockheed Martin', 'Industrials', 85, 'lockheedmartin.com'),
    ('DE', 'Deere', 'Industrials', 85, 'deere.com'),
    ('BX', 'Blackstone', 'Financials', 85, 'blackstone.com'),
    ('SO', 'Southern Company', 'Utilities', 85, 'southerncompany.com'),
    ('ICE', 'Intercontinental Exchange', 'Financials', 80, 'ice.com'),
    ('MO', 'Altria', 'Consumer Staples', 80, 'altria.com'),
    ('PLD', 'Prologis', 'Real Estate', 80, 'prologis.com'),
    ('DUK', 'Duke Energy', 'Utilities', 80, 'duke-energy.com'),
    ('SHW', 'Sherwin-Williams', 'Materials', 75, 'sherwin-williams.com'),
    ('CEG', 'Constellation Energy', 'Utilities', 80, 'constellationenergy.com'),
    ('MELI', 'MercadoLibre', 'Consumer Discretionary', 90, 'mercadolibre.com'),
    ('DASH', 'DoorDash', 'Consumer Discretionary', 90, 'doordash.com'),
    ('APP', 'AppLovin', 'Technology', 110, 'applovin.com'),
    ('ABNB', 'Airbnb', 'Consumer Discretionary', 75, 'airbnb.com'),
    ('MRVL', 'Marvell', 'Technology', 70, 'marvell.com'),
    ('EQIX', 'Equinix', 'Real Estate', 75, 'equinix.com'),
    ('AMT', 'American Tower', 'Real Estate', 90, 'americantower.com'),
    ('FCX', 'Freeport-McMoRan', 'Materials', 60, 'fcx.com'),
    ('NEM', 'Newmont', 'Materials', 60, 'newmont.com'),
    ('COP', 'ConocoPhillips', 'Energy', 120, 'conocophillips.com'),
    ('SLB', 'SLB', 'Energy', 55, 'slb.com'),
    ('EOG', 'EOG Resources', 'Energy', 65, 'eogresources.com'),
    ('PSX', 'Phillips 66', 'Energy', 50, 'phillips66.com'),
    ('MPC', 'Marathon Petroleum', 'Energy', 50, 'marathonpetroleum.com'),
    ('O', 'Realty Income', 'Real Estate', 50, 'realtyincome.com'),
    ('SPG', 'Simon Property', 'Real Estate', 55, 'simon.com'),
    ('AEP', 'American Electric Power', 'Utilities', 55, 'aep.com'),
    ('D', 'Dominion Energy', 'Utilities', 50, 'dominionenergy.com'),
    ('ECL', 'Ecolab', 'Materials', 65, 'ecolab.com'),
    ('APD', 'Air Products', 'Materials', 60, 'airproducts.com'),
    ('NKE', 'Nike', 'Consumer Discretionary', 95, 'nike.com'),
    ('TJX', 'TJX Companies', 'Consumer Discretionary', 135, 'tjx.com'),
    ('MDLZ', 'Mondelez', 'Consumer Staples', 80, 'mondelezinternational.com'),
    ('CL', 'Colgate-Palmolive', 'Consumer Staples', 70, 'colgatepalmolive.com'),
    ('CVS', 'CVS Health', 'Health Care', 70, 'cvshealth.com'),
    ('ELV', 'Elevance Health', 'Health Care', 75, 'elevancehealth.com'),
    ('SYK', 'Stryker', 'Health Care', 140, 'stryker.com'),
    ('GEV', 'GE Vernova', 'Industrials', 130, 'gevernova.com'),
    ('PH', 'Parker Hannifin', 'Industrials', 85, 'parker.com'),
    ('TT', 'Trane Technologies', 'Industrials', 90, 'tranetechnologies.com'),
]

NASDAQ100_TICKERS = {
    'NVDA', 'MSFT', 'AAPL', 'GOOGL', 'AMZN', 'META', 'AVGO', 'TSLA', 'NFLX', 'COST',
    'PLTR', 'AMD', 'TMUS', 'CSCO', 'CRM', 'INTU', 'QCOM', 'TXN', 'ISRG', 'BKNG',
    'AMGN', 'ADBE', 'AMAT', 'PEP', 'GILD', 'MU', 'LRCX', 'ADP', 'ANET', 'KLAC',
    'VRTX', 'SBUX', 'PANW', 'CRWD', 'INTC', 'ADI', 'MELI', 'ABNB', 'MRVL', 'APP',
    'DASH', 'MDLZ', 'CEG', 'HON', 'CMCSA',
}

SECTOR_ORDER = [
    'Technology', 'Financials', 'Health Care', 'Consumer Discretionary',
    'Communication Services', 'Industrials', 'Consumer Staples', 'Energy',
    'Utilities', 'Materials', 'Real Estate',
]


def constituents(index='sp500'):
    rows = SP500
    if index.lower() in ('ndx', 'nasdaq100', 'nasdaq'):
        rows = [r for r in SP500 if r[0] in NASDAQ100_TICKERS]
    return [{'ticker': t, 'name': n, 'sector': s, 'cap': c, 'domain': d}
            for t, n, s, c, d in rows]


# --------------------------------------------------- 2. CNN Fear & Greed ---

CNN_URL = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'

RATINGS = [
    (25, 'Extreme Fear'), (45, 'Fear'), (55, 'Neutral'),
    (75, 'Greed'), (101, 'Extreme Greed'),
]


def rating_for(score):
    for ceiling, label in RATINGS:
        if score < ceiling:
            return label
    return 'Extreme Greed'


# CNN's own labels for the seven inputs it combines.
COMPONENTS = [
    ('market_momentum_sp500', 'Market Momentum', 'S&P 500 vs its 125-day average'),
    ('stock_price_strength', 'Stock Price Strength', 'Net new 52-week highs on the NYSE'),
    ('stock_price_breadth', 'Stock Price Breadth', 'Volume in advancing vs declining stocks'),
    ('put_call_options', 'Put and Call Options', '5-day average put/call ratio'),
    ('market_volatility_vix', 'Market Volatility', 'VIX vs its 50-day average'),
    ('safe_haven_demand', 'Safe Haven Demand', 'Stock returns vs Treasury returns'),
    ('junk_bond_demand', 'Junk Bond Demand', 'Yield spread, junk vs investment grade'),
]


def fear_greed():
    """CNN's published index. Returns ok=False rather than inventing a number:
    a made-up sentiment reading is worse than an empty panel."""
    def build():
        try:
            r = requests.get(CNN_URL, headers=HEADERS, timeout=12)
            if not r.ok:
                return {'ok': False, 'error': f'CNN returned HTTP {r.status_code}'}
            data = r.json()
        except Exception as e:
            return {'ok': False, 'error': f'Could not reach CNN ({type(e).__name__})'}

        fg = data.get('fear_and_greed') or {}
        score = fg.get('score')
        if score is None:
            return {'ok': False, 'error': 'CNN response did not contain a score'}
        score = round(float(score))

        def prev(key):
            v = fg.get(key)
            return round(float(v)) if v is not None else None

        comps = []
        for key, label, blurb in COMPONENTS:
            node = data.get(key) or {}
            v = node.get('score')
            if v is None:
                continue
            comps.append({
                'key': key, 'label': label, 'blurb': blurb,
                'score': round(float(v)),
                'rating': node.get('rating') or rating_for(float(v)),
            })

        history = []
        for p in (fg.get('historical') or data.get('fear_and_greed_historical', {}).get('data') or [])[-90:]:
            if isinstance(p, dict) and p.get('y') is not None:
                history.append(round(float(p['y']), 1))

        return {
            'ok': True,
            'score': score,
            'rating': fg.get('rating') or rating_for(score),
            'updated': fg.get('timestamp'),
            'previous': {
                'close': prev('previous_close'),
                'week': prev('previous_1_week'),
                'month': prev('previous_1_month'),
                'year': prev('previous_1_year'),
            },
            'components': comps,
            'history': history,
            'source': 'CNN Business Fear & Greed Index',
        }

    return _cached('fg', 900, build)
