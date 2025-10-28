from flask import Flask
import requests
import pandas as pd
import schedule
import time
import threading
from datetime import datetime
from smartmoneyconcepts.smc import smc_indicators  # pip install git+https://github.com/joshyattridge/smart-money-concepts.git

app = Flask(__name__)

API_URL = "https://brsapi.ir/Api/Market/Gold_Currency.php?key=BFnYYJjKvtuvPhtIZ2WfyFNhE54TG6ly"
TELEGRAM_TOKEN = "8296855766:AAEAOO_NA2Q0GROFMKACAVV2ZnkxvDBroWM"
CHAT_ID = "249634530"  # Chat ID ارائه‌شده
price_history = []  # لیست برای ذخیره زمان و قیمت‌ها
signals = []  # لیست (message_id, entry_price, signal_type, send_time)

def fetch_gold_price():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()
        for item in data.get('gold', []):
            if item['symbol'] == 'IR_GOLD_MELTED':
                return float(item['price']), item.get('time_unix', time.time())
        return None, None
    except requests.RequestException:
        return None, None

def is_active_period():
    now = datetime.now().hour
    return 10 <= now < 19 or 22 <= now or now < 7  # 10AM-7PM یا 10PM-7AM

def analyze_and_signal():
    if not is_active_period():
        return
    price, timestamp = fetch_gold_price()
    if price:
        price_history.append({'timestamp': timestamp, 'price': price})
        df = pd.DataFrame(price_history)
        if len(df) < 10:
            return
        
        # اعمال اندیکاتورهای SMC/ICT/RTM (ساده‌شده: تشخیص FVG، Order Blocks)
        try:
            indicators = smc_indicators(df)  # فرض بر OHLC؛ close=price تطبیق دهید
            fvg = indicators['FVG'].iloc[-1]
            ob = indicators['OrderBlocks'].iloc[-1]
            if fvg > 0 and ob > 0:  # سیگنال صعودی ساده
                signal = 'BUY'
            elif fvg < 0 and ob < 0:  # نزولی
                signal = 'SELL'
            else:
                return
            
            # محاسبه TP/SL: 1.5% سود، 1% ضرر
            entry = price
            if signal == 'BUY':
                tp = entry * 1.015
                sl = entry * 0.99
            else:
                tp = entry * 0.985
                sl = entry * 1.01
            
            # ارسال سیگنال
            message = f"{signal} طلای آب‌شده در {entry}. TP: {tp}, SL: {sl}. قیمت لحظه‌ای: {price}"
            send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}"
            resp = requests.get(send_url).json()
            if resp.get('ok'):
                msg_id = resp['result']['message_id']
                signals.append((msg_id, entry, signal, time.time()))
                # زمان‌بندی حذف و P/L پس از 6 ساعت
                threading.Timer(21600, handle_signal_end, args=(msg_id, entry, signal)).start()
        except Exception:
            pass  # در صورت خطا در تحلیل، ادامه می‌دهد

def handle_signal_end(msg_id, entry, signal):
    current, _ = fetch_gold_price()
    if current:
        direction = 1 if signal == 'BUY' else -1
        pl = direction * (current - entry) / entry * 100  # درصد P/L
        reply_text = f"پایان سیگنال. سود/زیان: {pl:.2f}%"
        reply_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={reply_text}&reply_to_message_id={msg_id}"
        requests.get(reply_url)
        # حذف پیام
        delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage?chat_id={CHAT_ID}&message_id={msg_id}"
        requests.get(delete_url)

def scheduler_thread():
    schedule.every(2).minutes.do(analyze_and_signal)
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route('/')
def home():
    return "ربات فعال است!"

if __name__ == '__main__':
    threading.Thread(target=scheduler_thread, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)