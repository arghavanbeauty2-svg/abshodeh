from flask import Flask, request
import requests
import pandas as pd
import pandas_ta as ta
import schedule
import time
import threading
import logging
from datetime import datetime
import json

# تنظیم لاگ‌گیری دقیق
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

app = Flask(__name__)

# تنظیمات
API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
price_history = []
last_update_id = 0
active_chats = set()  # ذخیره chat_id کاربران فعال

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
            logging.warning(f"تلاش {attempt+1} دریافت قیمت شکست: {e}")
            time.sleep(2)
    logging.error("دریافت قیمت کاملاً شکست خورد")
    return None, None

# --- ارسال پیام با دکمه ---
def send_price_with_button(chat_id):
    price, _ = fetch_gold_price()
    if not price:
        send_telegram(chat_id, "⚠️ خطا در دریافت قیمت. دوباره تلاش کنید.")
        return None
    message = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nبرای بروزرسانی کلیک کنید 👇"
    keyboard = {
        "inline_keyboard": [[
            {"text": "🔄 استعلام مجدد", "callback_data": "get_price"}
        ]]
    }
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, timeout=10).json()
        if resp.get('ok'):
            msg_id = resp['result']['message_id']
            logging.info(f"پیام با دکمه ارسال شد به {chat_id} - ID: {msg_id}")
            return msg_id
        else:
            logging.error(f"ارسال پیام شکست: {resp}")
    except Exception as e:
        logging.error(f"خطا در ارسال دکمه: {e}")
    return None

# --- ویرایش پیام ---
def edit_price_message(chat_id, message_id):
    price, _ = fetch_gold_price()
    if not price:
        return
    new_text = f"💰 **قیمت لحظه‌ای طلای آب‌شده**\n`{price:,.0f} تومان`\n\nبرای بروزرسانی کلیک کنید 👇"
    keyboard = {
        "inline_keyboard": [[
            {"text": "🔄 استعلام مجدد", "callback_data": "get_price"}
        ]]
    }
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': new_text,
        'parse_mode': 'Markdown',
        'reply_markup': json.dumps(keyboard)
    }
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText", data=payload, timeout=10).json()
        if resp.get('ok'):
            logging.info(f"قیمت بروز شد برای {chat_id}")
        else:
            logging.error(f"ویرایش پیام شکست: {resp}")
    except Exception as e:
        logging.error(f"خطا در ویرایش: {e}")

# --- ارسال پیام ساده ---
def send_telegram(chat_id, text, reply_to=None):
    payload = {'chat_id': chat_id, 'text': text}
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=payload, timeout=10).json()
        if resp.get('ok'):
            return resp['result']['message_id']
    except Exception as e:
        logging.error(f"ارسال پیام ساده شکست: {e}")
    return None

# --- polling تلگرام ---
def telegram_polling():
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {'offset': last_update_id + 1, 'timeout': 30}
    logging.info("Polling تلگرام شروع شد...")
    while True:
        try:
            response = requests.get(url, params=params, timeout=35).json()
            if not response.get('ok'):
                logging.warning(f"getUpdates خطا: {response}")
                time.sleep(5)
                continue
            for update in response.get('result', []):
                last_update_id = update['update_id']
                logging.info(f"آپدیت دریافت شد: {update.get('update_id')}")
                
                if 'message' in update:
                    message = update['message']
                    chat_id = message['chat']['id']
                    text = message.get('text', '').strip()
                    active_chats.add(chat_id)
                    
                    if text == '/start':
                        send_telegram(chat_id, "✅ ربات فعال شد! قیمت لحظه‌ای:")
                        send_price_with_button(chat_id)
                    else:
                        send_telegram(chat_id, "دستور ناشناخته. /start بزنید.")
                
                elif 'callback_query' in update:
                    callback = update['callback_query']
                    chat_id = callback['message']['chat']['id']
                    message_id = callback['message']['message_id']
                    data = callback['data']
                    callback_id = callback['id']
                    
                    if data == 'get_price':
                        edit_price_message(chat_id, message_id)
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                            data={'callback_query_id': callback_id}
                        )
        except Exception as e:
            logging.error(f"Polling خطا: {e}")
            time.sleep(5)

# --- توابع سیگنال (به همه کاربران فعال) ---
def is_active_period():
    now = datetime.now().hour
    return 10 <= now < 19 or 22 <= now or now < 7

def detect_fvg(df):
    if len(df) < 3: return 0
    current = df['price'].iloc[-1]
    prev2 = df['price'].iloc[-3]
    return 1 if current > prev2 else -1 if current < prev2 else 0

def detect_order_block(df):
    if len(df) < 5: return 0
    window = df['price'].iloc[-5:]
    recent_high, recent_low = window.max(), window.min()
    current = df['price'].iloc[-1]
    range_val = recent_high - recent_low
    if range_val == 0: return 0
    return -1 if abs(current - recent_high) < range_val * 0.1 else 1 if abs(current - recent_low) < range_val * 0.1 else 0

def calculate_tp_sl(entry, atr, signal):
    multiplier = atr * 1.5 if atr and not pd.isna(atr) else entry * 0.015
    if signal == 'BUY':
        return round(entry + multiplier), round(entry - multiplier * 0.67)
    else:
        return round(entry - multiplier), round(entry + multiplier * 0.67)

def analyze_and_signal():
    if not is_active_period() or not active_chats:
        return
    price, timestamp = fetch_gold_price()
    if not price: return
    price_history.append({'timestamp': timestamp, 'price': price})
    if len(price_history) > 200: price_history.pop(0)
    
    df = pd.DataFrame(price_history[-50:])
    if len(df) < 20: return
    
    df['high'] = df['low'] = df['close'] = df['price']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    atr = df['atr'].iloc[-1]
    
    fvg = detect_fvg(df)
    ob = detect_order_block(df)
    
    if (fvg > 0 and ob > 0) or (fvg < 0 and ob < 0):
        signal = 'BUY' if fvg > 0 else 'SELL'
        entry = price
        tp, sl = calculate_tp_sl(entry, atr, signal)
        message = f"🚨 {signal} طلای آب‌شده\nورود: {entry:,.0f}\nTP: {tp:,.0f}\nSL: {sl:,.0f}\nقیمت: {price:,.0f}"
        
        for chat_id in active_chats:
            msg_id = send_telegram(chat_id, message)
            if msg_id:
                threading.Timer(21600, lambda: handle_signal_end(chat_id, entry, signal, msg_id)).start()

def handle_signal_end(chat_id, entry, signal, msg_id):
    current, _ = fetch_gold_price()
    if not current: return
    direction = 1 if signal == 'BUY' else -1
    pl = direction * (current - entry) / entry * 100
    reply_text = f"✅ پایان سیگنال {signal}\nسود/زیان: {pl:+.2f}%\nقیمت: {current:,.0f}"
    send_telegram(chat_id, reply_text, reply_to=msg_id)
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage", 
                  data={'chat_id': chat_id, 'message_id': msg_id})

# --- scheduler ---
def scheduler_thread():
    schedule.every(2).minutes.do(analyze_and_signal)
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- صفحه اصلی ---
@app.route('/')
def home():
    return "ربات فعال! به تلگرام بروید و /start بزنید."

# --- اجرا ---
if __name__ == '__main__':
    threading.Thread(target=scheduler_thread, daemon=True).start()
    threading.Thread(target=telegram_polling, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
