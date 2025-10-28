from flask import Flask
import requests
import pandas as pd
import pandas_ta as ta  # برای ATR
import schedule
import time
import threading
import logging
from datetime import datetime

# تنظیم لاگ‌گیری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
CHAT_ID = "249634530"  # Chat ID شما
price_history = []  # تاریخچه قیمت‌ها

def fetch_gold_price(retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(API_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            for item in data.get('gold', []):
                if item['symbol'] == 'IR_GOLD_MELTED':
                    price = float(item['price'])
                    timestamp = item.get('time_unix', time.time())
                    logging.info(f"قیمت دریافت شد: {price}")
                    return price, timestamp
        except Exception as e:
            logging.warning(f"تلاش {attempt+1} شکست: {e}")
            time.sleep(2)
    logging.error("دریافت قیمت شکست خورد")
    return None, None

def is_active_period():
    now = datetime.now().hour
    return 10 <= now < 19 or 22 <= now or now < 7

def detect_fvg(df):
    if len(df) < 3:
        return 0
    current = df['price'].iloc[-1]
    prev2 = df['price'].iloc[-3]
    if current > prev2:
        return 1  # FVG صعودی
    elif current < prev2:
        return -1  # FVG نزولی
    return 0

def detect_order_block(df):
    if len(df) < 5:
        return 0
    window = df['price'].iloc[-5:]
    recent_high = window.max()
    recent_low = window.min()
    current = df['price'].iloc[-1]
    range_val = recent_high - recent_low
    if range_val == 0:
        return 0
    if abs(current - recent_high) < range_val * 0.1:
        return -1  # نزدیک بالا → نزولی
    elif abs(current - recent_low) < range_val * 0.1:
        return 1  # نزدیک پایین → صعودی
    return 0

def calculate_tp_sl(entry, atr, signal):
    multiplier = atr * 1.5 if atr else entry * 0.015  # fallback
    if signal == 'BUY':
        tp = entry + multiplier
        sl = entry - (multiplier * 0.67)  # ریسک ۱:۱.۵
    else:
        tp = entry - multiplier
        sl = entry + (multiplier * 0.67)
    return round(tp), round(sl)

def analyze_and_signal():
    if not is_active_period():
        return
    price, timestamp = fetch_gold_price()
    if not price:
        return
    price_history.append({'timestamp': timestamp, 'price': price})
    if len(price_history) > 200:
        price_history.pop(0)
    
    df = pd.DataFrame(price_history[-50:])  # ۵۰ داده اخیر
    if len(df) < 20:
        return
    
    # محاسبه ATR برای TP/SL پویا
    df['atr'] = ta.atr(df['price'], df['price'], df['price'], length=14)
    atr = df['atr'].iloc[-1] if not pd.isna(df['atr'].iloc[-1]) else None
    
    fvg = detect_fvg(df)
    ob = detect_order_block(df)
    
    if fvg > 0 and ob > 0:
        signal = 'BUY'
    elif fvg < 0 and ob < 0:
        signal = 'SELL'
    else:
        return
    
    entry = price
    tp, sl = calculate_tp_sl(entry, atr, signal)
    
    message = f"🚨 {signal} طلای آب‌شده\nورود: {entry:,.0f}\nTP: {tp:,.0f}\nSL: {sl:,.0f}\nقیمت فعلی: {price:,.0f}"
    if send_telegram(message, reply_to=None):
        threading.Timer(21600, handle_signal_end, args=(entry, signal)).start()
        logging.info(f"سیگنال {signal} ارسال شد")

def send_telegram(text, reply_to=None, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text}
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    for attempt in range(retries):
        try:
            resp = requests.post(url, data=payload, timeout=10).json()
            if resp.get('ok'):
                return resp['result']['message_id']
        except Exception as e:
            logging.warning(f"تلگرام تلاش {attempt+1} شکست: {e}")
            time.sleep(2)
    logging.error("ارسال تلگرام شکست")
    return None

def handle_signal_end(entry, signal):
    current, _ = fetch_gold_price()
    if not current:
        return
    direction = 1 if signal == 'BUY' else -1
    pl = direction * (current - entry) / entry * 100
    reply_text = f"✅ پایان سیگنال {signal}\nسود/زیان: {pl:+.2f}%\nقیمت فعلی: {current:,.0f}"
    send_telegram(reply_text)
    logging.info(f"پایان سیگنال: {pl:+.2f}%")

def scheduler_thread():
    schedule.every(2).minutes.do(analyze_and_signal)
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route('/')
def home():
    return "ربات طلای آب‌شده فعال و بدون خطا!"

if __name__ == '__main__':
    threading.Thread(target=scheduler_thread, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
