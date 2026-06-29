from flask import Flask, render_template, jsonify, request
import os
import pandas as pd
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

FINNHUB_KEY = os.environ.get('FINNHUB_KEY', 'd91d95pr01qqfqkb97vgd91d95pr01qqfqkb9800')
FINNHUB = 'https://finnhub.io/api/v1'


def fh(path, **params):
    params['token'] = FINNHUB_KEY
    r = requests.get(f'{FINNHUB}{path}', params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def candles_df(ticker, resolution, from_ts, to_ts):
    data = fh('/stock/candle', symbol=ticker.upper(), resolution=resolution,
              **{'from': from_ts, 'to': to_ts})
    if data.get('s') != 'ok' or not data.get('c'):
        return pd.DataFrame()
    df = pd.DataFrame({
        'Open': data['o'], 'High': data['h'], 'Low': data['l'],
        'Close': data['c'], 'Volume': data['v'],
        'Time': [datetime.utcfromtimestamp(t) for t in data['t']]
    }).set_index('Time')
    return df


def period_to_resolution(period):
    return {
        '1d': ('1', 1), '5d': ('5', 5), '1mo': ('D', 30),
        '3mo': ('D', 90), '6mo': ('D', 180), '1y': ('W', 365),
        '2y': ('W', 730), '5y': ('M', 1825),
    }.get(period, ('D', 30))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        now = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=60)).timestamp())
        hist = candles_df(ticker, 'D', from_ts, now)
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

        profile = fh('/stock/profile2', symbol=ticker.upper())
        name = profile.get('name', ticker.upper())
        sector = profile.get('finnhubIndustry', '')

        dy, ex = 0, None
        try:
            div_data = fh('/stock/dividend', symbol=ticker.upper(),
                          **{'from': (datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d'),
                             'to': datetime.utcnow().strftime('%Y-%m-%d')})
            if div_data:
                last = div_data[-1]
                amount = last.get('amount', 0) or 0
                dy = round(amount / price, 4) if price else 0
                ex = last.get('exDate', None)
        except Exception:
            pass

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
        resolution, days = period_to_resolution(period)
        now = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        hist = candles_df(ticker, resolution, from_ts, now)
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
        to_date = datetime.utcnow().strftime('%Y-%m-%d')
        from_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
        news = fh('/company-news', symbol=ticker.upper(),
                  **{'from': from_date, 'to': to_date})
        return jsonify([{
            'title': n.get('headline', ''),
            'link': n.get('url', ''),
            'publisher': n.get('source', ''),
            'time': n.get('datetime', 0)
        } for n in (news or [])[:8]])
    except Exception:
        return jsonify([])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
