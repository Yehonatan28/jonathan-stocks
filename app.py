import os
from flask import Flask, render_template, jsonify, request
import yfinance as yf
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
stock.session = None
        hist = stock.history(period='1mo')
        info = stock.info

        if hist.empty:
            return jsonify({'error': 'מניה לא נמצאה'}), 404

        close = hist['Close']
        
        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        rsi = round(float(100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-10)))), 1)

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_bullish = bool(macd.iloc[-1] > signal.iloc[-1])

        # ATR
        hi = hist['High']
        lo = hist['Low']
        tr = (hi - lo).ewm(span=14).mean()
        atr_pct = round(float(tr.iloc[-1] / close.iloc[-1] * 100), 2)

        # Bollinger
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        bb_pct = round(float((close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1] + 1e-10) * 100), 1)

        # Volume
        vol_ratio = round(float(hist['Volume'].iloc[-1] / hist['Volume'].mean()), 2)

        price = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2)
        chg = round((price - prev) / prev * 100, 2)
        atr_abs = price * atr_pct / 100

        # Recommendation
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

        return jsonify({
            'ticker': ticker.upper(),
            'name': info.get('longName', ticker),
            'sector': info.get('sector', ''),
            'price': price,
            'chg': chg,
            'rsi': rsi,
            'macd': 'BULLISH' if macd_bullish else 'BEARISH',
            'atr_pct': atr_pct,
            'bb_pct': bb_pct,
            'vol_ratio': vol_ratio,
            'rec': rec,
            'conf': conf,
            'entry': price,
            'target': round(price + 2 * atr_abs, 2),
            'stop': round(price - 1.5 * atr_abs, 2),
            'support': round(float(hist['Low'].rolling(20).min().iloc[-1]), 2),
            'resistance': round(float(hist['High'].rolling(20).max().iloc[-1]), 2),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
   app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

