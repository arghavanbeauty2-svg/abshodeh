from flask import Flask, request, jsonify
import requests
import pandas as pd
import pandas_ta as ta
import schedule
import time
import threading
import logging
from datetime import datetime
import json

# تنظیم لاگ‌گیری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# تنظیمات
API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
CHAT_ID = "249634530"
WEBHOOK_URL = "https://abshodeh.onrender.com/webhook"  # تغییر دهید اگر URL متفاوت است
price_history = []

# --- دریافت قیمت ---
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
                    logging.info(f"قیمت دریافت شد: {price:,.0f}")
                    return price, timestamp
        except Exception as e:
            logging.warning(f"تلاش {attempt+1} شکست: {e}")
            time.sleep(2)
    logging.error("دریافت قیمت شکست")
    return None, None

# --- بازه فعال ---
def is_active_period():
    now = datetime.now().hour
    return 10 <= now < 19 or 22 <= now or now < 7

# --- تشخیص FVG ---
def detect_fvg(df):
    if len(df) < 3:
        return 0
    current = df['price'].iloc[-1]
    prev2 = df['price'].iloc[-3]
    if current > prev2:
        return 1
    elif current < prev2:
        return -1
    return 0

# --- تشخیص Order Block ---
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
        return -1
    elif abs(current - recent_low) < range_val * 0.1:
        return 1
    return 0

# --- محاسبه TP/SL ---
def calculate_tp_sl(entry, atr, signal):
    if atr and not pd.isna(atr):
        multiplier = atr * 1.5
    else:
        multiplier = entry * 0.015
    if signal == 'BUY':
        tp = entry + multiplier
        sl = entry - (multiplier * 0.67)
    else:
        tp = entry - multiplier
        sl = entry + (multiplier * 0.67)
    return round(tp), round(sl)

# --- تحلیل و سیگنال ---
def analyze_and_signal():
    if not is_active_period():
        logging.info("خارج از بازه فعال — تحلیل متوقف شد")
        return
    price, timestamp = fetch_gold_price()
    if not price:
        return
    price_history.append({'timestamp': timestamp, 'price': price})
    if len(price_history) > 200:
        price_history.pop(0)
    
    df = pd.DataFrame(price_history[-50:])
    if len(df) < 20:
        return
    
    df['high'] = df['price']
    df['low'] = df['price']
    df['close'] = df['price']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    atr = df['atr'].iloc[-1]
    
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
    msg_id = send_telegram(message)
    if msg_id:
        threading.Timer(21600, handle_signal_end, args=(entry, signal, msg_id)).start()
        logging.info(f"سیگنال {signal} ارسال شد - ID: {msg_id}")

# --- پایان سیگنال ---
def handle_signal_end(entry, signal, msg_id):
    current, _ = fetch_gold_price()
    if not current:
        return
    direction = 1 if signal == 'BUY' else -1
    pl = direction * (current - entry) / entry * 100
    reply_text = f"✅ پایان سیگنال {signal}\nسود/زیان: {pl:+.2f}%\nقیمت فعلی: {current:,.0f}"
    send_telegram(reply_text, reply_to=msg_id)
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    requests.post(delete_url, data={'chat_id': CHAT_ID, 'message_id': msg_id})
    logging.info(f"سیگنال {signal} پایان یافت - P/L: {pl:+.2f}%")

# --- ارسال پیام تلگرام ---
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
            logging.warning(f"تلاش {attempt+1} ارسال شکست: {e}")
            time.sleep(2)
    logging.error("ارسال پیام تلگرام شکست")
    return None

# --- ارسال پیام با دکمه ---
def send_price_with_button():
    price, _ = fetch_gold_price()
    if not price:
        return
    message = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nبرای بروزرسانی دوباره کلیک کنید 👇"
    keyboard = {
        "inline_keyboard": [[
            {"text": "🔄 استعلام مجدد", "callback_data": "get_price"}
        ]]
    }
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload)
        logging.info("پیام با دکمه ارسال شد")
    except Exception as e:
        logging.error(f"ارسال دکمه شکست: {e}")

# --- پاسخ به کلیک دکمه ---
def answer_callback(callback_query_id, price):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
            data={'callback_query_id': callback_query_id, 'text': f"قیمت بروز شد: {price:,.0f}"}
        )
    except Exception as e:
        logging.error(f"answerCallbackQuery شکست: {e}")

# --- وب‌هوک ---
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if 'callback_query' in update:
        callback_query = update['callback_query']
        data = callback_query['data']
        chat_id = callback_query['message']['chat']['id']
        message_id = callback_query['message']['message_id']
        callback_id = callback_query['id']

        if data == "get_price":
            price, _ = fetch_gold_price()
            if price:
                new_text = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nبرای بروزرسانی دوباره کلیک کنید 👇"
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "🔄 استعلام مجدد", "callback_data": "get_price"}
                    ]]
                }
                edit_payload = {
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': new_text,
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps(keyboard)
                }
                try:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=edit_payload)
                    answer_callback(callback_id, price)
                    logging.info(f"قیمت بروز شد: {price:,.0f}")
                except Exception as e:
                    logging.error(f"ویرایش پیام شکست: {e}")
    return jsonify({"status": "ok"})

# --- تنظیم وب‌هوک ---
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    payload = {'url': WEBHOOK_URL}
    try:
        response = requests.post(url, data=payload).json()
        if response.get('ok'):
            logging.info("وب‌هوک تنظیم شد")
        else:
            logging.error(f"تنظیم وب‌هوک شکست: {response}")
    except Exception as e:
        logging.error(f"خطا در وب‌هوک: {e}")

# --- صفحه اصلی ---
@app.route('/')
def home():
    return "ربات طلای آب‌شده فعال است! دکمه استعلام قیمت اضافه شد."

# --- scheduler ---
def scheduler_thread():
    schedule.every(2).minutes.do(analyze_and_signal)
    # ارسال پیام با دکمه در استارت
    threading.Timer(10, send_price_with_button).start()
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- اجرا ---
if __name__ == '__main__':
    threading.Thread(target=scheduler_thread, daemon=True).start()
    set_webhook()
    app.run(host='0.0.0.0', port=5000)
