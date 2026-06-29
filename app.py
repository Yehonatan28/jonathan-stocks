from flask import Flask, render_template, jsonify, request
import os
import requests
import pandas as pd

app = Flask(__name__)

AV_KEY = os.environ.get('AV_KEY', 'demo')
AV_BASE = 'https://www.alphavantage.co/query'

def av(params):
    params['apikey'] = AV_KEY
    r = requests.get(AV_BASE, params=params, timeout=15)
    return r.json()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        data = av({'function': 'TIME_SERIES_DAILY', 'symbol': ticker, 'outputsize': 'compact'})
        if 'Error Message' in data or 'Note' in data:
            return jsonify({'error': 'מניה לא נמצאה'}), 404
        ts = data.get('Time Series (Daily)', {})
        if not ts:
            return jsonify({'error': 'אין נתונים'}), 404
        dates = sorted(ts.keys(), reverse=True)[:30]
        closes = [float(ts[d]['4. close']) for d in dates]
        highs = [float(ts[d]['2. high']) for d in dates]
        lows = [float(ts[d]['3. low']) for d in dates]
        vols = [int(ts[d]['5. volume']) for d in dates]
        close = pd.Series(closes[::-1])
        high = pd.Series(highs[::-1])
        low = pd.Series(lows[::-1])
        vol = pd.Series(vols[::-1])
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi = round(float(100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-10)))), 1)
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_bullish = bool(macd.iloc[-1] > signal.iloc[-1])
        tr = (high - low).ewm(span=14).mean()
        atr_pct = round(float(tr.iloc[-1] / close.iloc[-1] * 100), 2)
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        bb_pct = round(float((close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1] + 1e-10) * 100), 1)
        vol_ratio = round(float(vol.iloc[-1] / vol.mean()), 2)
        price = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        chg = round((price - prev) / prev * 100, 2)
        atr_abs = price * atr_pct / 100
        score = 0
        if rsi < 35: score += 3
        elif rsi < 50: score += 2
        elif rsi > 72: score -= 3
        elif rsi > 65: score -= 1
        if macd_bullish: score += 2
        else: score -= 2
        if bb_pct < 20: score += 2
        elif bb_pct > 85: score -= 2
        if vol_ratio > 1.4: score += 1
        if score >= 4: rec = 'BUY'
        elif score <= -3: rec = 'SELL'
        else: rec = 'WAIT'
        conf = min(95, max(40, 55 + score * 7))
        overview = av({'function': 'OVERVIEW', 'symbol': ticker})
        name = overview.get('Name', ticker)
        sector = overview.get('Sector', '')
        div_yield = float(overview.get('DividendYield', 0) or 0)
        ex_div = overview.get('ExDividendDate', None)
        history = [round(float(p), 2) for p in close.tolist()]
        return jsonify({
            'ticker': ticker.upper(), 'name': name, 'sector': sector,
            'price': price, 'chg': chg, 'rsi': rsi,
            'macd': 'BULLISH' if macd_bullish else 'BEARISH',
            'atr_pct': atr_pct, 'bb_pct': bb_pct, 'vol_ratio': vol_ratio,
            'rec': rec, 'conf': conf, 'entry': price,
            'target': round(price + 2 * atr_abs, 2),
            'stop': round(price - 1.5 * atr_abs, 2),
            'support': round(float(low.rolling(20).min().iloc[-1]), 2),
            'resistance': round(float(high.rolling(20).max().iloc[-1]), 2),
            'dividend_yield': round(div_yield, 4),
            'ex_dividend_date': ex_div,
            'history': history,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chart/<ticker>')
def get_chart(ticker):
    try:
        period = request.args.get('period', '1mo')
        if period in ['1d', '5d']:
            data = av({'function': 'TIME_SERIES_INTRADAY', 'symbol': ticker, 'interval': '60min', 'outputsize': 'compact'})
            ts_key = 'Time Series (60min)'
        elif period in ['1mo', '3mo', '6mo']:
            data = av({'function': 'TIME_SERIES_DAILY', 'symbol': ticker, 'outputsize': 'compact'})
            ts_key = 'Time Series (Daily)'
        else:
            data = av({'function': 'TIME_SERIES_WEEKLY', 'symbol': ticker})
            ts_key = 'Weekly Time Series'
        ts = data.get(ts_key, {})
        if not ts:
            return jsonify({'error': 'אין נתונים'}), 404
        limit = {'1d':24,'5d':120,'1mo':30,'3mo':90,'6mo':180,'1y':52,'2y':104,'5y':260}.get(period, 30)
        dates = sorted(ts.keys())[-limit:]
        candles = []
        for d in dates:
            row = ts[d]
            candles.append({'t':d[:10],'o':float(row.get('1. open',0)),'h':float(row.get('2. high',0)),'l':float(row.get('3. low',0)),'c':float(row.get('4. close',0)),'v':int(row.get('5. volume',0))})
        close = pd.Series([c['c'] for c in candles])
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi_s = (100-(100/(1+gain/(loss+1e-10)))).round(1).tolist()
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_l = (ema12-ema26).round(4).tolist()
        sig_l = (ema12-ema26).ewm(span=9).mean().round(4).tolist()
        ma20 = close.rolling(20).mean().round(2).tolist()
        return jsonify({'candles':candles,'rsi':rsi_s,'macd':macd_l,'signal':sig_l,'ma20':ma20})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/<ticker>')
def get_news(ticker):
    try:
        data = av({'function': 'NEWS_SENTIMENT', 'tickers': ticker, 'limit': '8'})
        feed = data.get('feed', [])
        return jsonify([{'title':n.get('title',''),'link':n.get('url',''),'publisher':n.get('source',''),'time':n.get('time_published','')} for n in feed[:8]])
    except Exception as e:
        return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    