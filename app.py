from flask import Flask, render_template, jsonify, request
import os
import pandas as pd
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

YF = 'https://query1.finance.yahoo.com/v8/finance/chart'
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def yf_chart(ticker, interval, range_):
    r = requests.get(f'{YF}/{ticker}', headers=HEADERS,
                     params={'interval': interval, 'range': range_}, timeout=10)
    r.raise_for_status()
    data = r.json()['chart']['result'][0]
    quotes = data['indicators']['quote'][0]
    timestamps = data['timestamps']
    df = pd.DataFrame({
        'Open': quotes['open'], 'High': quotes['high'], 'Low': quotes['low'],
        'Close': quotes['close'], 'Volume': quotes['volume'],
        'Time': [datetime.utcfromtimestamp(t) for t in timestamps]
    }).dropna().set_index('Time')
    return df


def period_params(period):
    return {
        '1d': ('5m', '1d'), '5d': ('15m', '5d'), '1mo': ('1d', '1mo'),
        '3mo': ('1d', '3mo'), '6mo': ('1d', '6mo'), '1y': ('1wk', '1y'),
        '2y': ('1wk', '2y'), '5y': ('1mo', '5y'),
    }.get(period, ('1d', '1mo'))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        hist = yf_chart(ticker, '1d', '3mo')
        if hist.empty:
            return jsonify({'error': 'מניה לא נמצאה'}), 404

        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']

        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi = round(float(100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-10)))), 1)

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_b = bool(macd.iloc[-1] > signal.iloc[-1])

        tr = (high - low).ewm(span=14).mean()
        atr_pct = round(float(tr.iloc[-1] / close.iloc[-1] * 100), 2)

        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_u = ma20 + 2 * std20
        bb_l = ma20 - 2 * std20
        bb_pct = round(float((close.iloc[-1] - bb_l.iloc[-1]) / (bb_u.iloc[-1] - bb_l.iloc[-1] + 1e-10) * 100), 1)

        vol_ratio = round(float(vol.iloc[-1] / vol.mean()), 2)
        price = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        chg = round((price - prev) / prev * 100, 2)
        atr_abs = price * atr_pct / 100

        sc = 0
        if rsi < 35: sc += 3
        elif rsi < 50: sc += 2
        elif rsi > 72: sc -= 3
        elif rsi > 65: sc -= 1
        if macd_b: sc += 2
        else: sc -= 2
        if bb_pct < 20: sc += 2
        elif bb_pct > 85: sc -= 2
        if vol_ratio > 1.4: sc += 1
        if sc >= 4: rec = 'BUY'
        elif sc <= -3: rec = 'SELL'
        else: rec = 'WAIT'
        conf = min(95, max(40, 55 + sc * 7))

        r2 = requests.get(f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                          headers=HEADERS, params={'modules': 'assetProfile,summaryDetail'}, timeout=10)
        info = r2.json().get('quoteSummary', {}).get('result', [{}])[0] if r2.ok else {}
        profile = info.get('assetProfile', {})
        summary = info.get('summaryDetail', {})
        name = ticker.upper()
        sector = profile.get('sector', '')
        dy = round(float(summary.get('dividendYield', {}).get('raw', 0) or 0), 4)
        ex = summary.get('exDividendDate', {}).get('fmt', None)

        return jsonify({
            'ticker': ticker.upper(), 'name': name, 'sector': sector,
            'price': price, 'chg': chg, 'rsi': rsi,
            'macd': 'BULLISH' if macd_b else 'BEARISH',
            'atr_pct': atr_pct, 'bb_pct': bb_pct, 'vol_ratio': vol_ratio,
            'rec': rec, 'conf': conf, 'entry': price,
            'target': round(price + 2 * atr_abs, 2),
            'stop': round(price - 1.5 * atr_abs, 2),
            'support': round(float(low.rolling(20).min().iloc[-1]), 2),
            'resistance': round(float(high.rolling(20).max().iloc[-1]), 2),
            'dividend_yield': dy, 'ex_dividend_date': ex,
            'history': [round(float(p), 2) for p in close.tolist()],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<ticker>')
def get_chart(ticker):
    try:
        period = request.args.get('period', '1mo')
        interval, range_ = period_params(period)
        hist = yf_chart(ticker, interval, range_)
        if hist.empty:
            return jsonify({'error': 'אין נתונים'}), 404

        candles = [{'t': idx.strftime('%Y-%m-%d'), 'o': round(float(r['Open']), 2),
                    'h': round(float(r['High']), 2), 'l': round(float(r['Low']), 2),
                    'c': round(float(r['Close']), 2), 'v': int(r['Volume'])}
                   for idx, r in hist.iterrows()]

        close = pd.Series([c['c'] for c in candles])
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi = (100 - (100 / (1 + gain / (loss + 1e-10)))).round(1).tolist()
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = (ema12 - ema26).round(4).tolist()
        sig_line = (ema12 - ema26).ewm(span=9).mean().round(4).tolist()
        ma20 = close.rolling(20).mean().round(2).tolist()

        return jsonify({'candles': candles, 'rsi': rsi, 'macd': macd_line,
                        'signal': sig_line, 'ma20': ma20})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/news/<ticker>')
def get_news(ticker):
    try:
        r = requests.get(f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                         headers=HEADERS, params={'modules': 'topHoldings'}, timeout=10)
        news_r = requests.get(f'https://query2.finance.yahoo.com/v1/finance/search',
                              headers=HEADERS, params={'q': ticker, 'newsCount': 8}, timeout=10)
        news = news_r.json().get('news', []) if news_r.ok else []
        return jsonify([{
            'title': n.get('title', ''),
            'link': n.get('link', ''),
            'publisher': n.get('publisher', ''),
            'time': n.get('providerPublishTime', 0)
        } for n in news[:8]])
    except Exception:
        return jsonify([])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
