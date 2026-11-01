import os
import requests
import random
import schedule
import time
import threading
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)
PAGE_TOKEN = os.environ.get("PAGE_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GRAPH_URL = "https://graph.facebook.com/v21.0/me/messages"

# --- LƯU TRỮ TẠM THỜI (In-memory) ---
users_db = {} # {psid: {"balance": 1000, "last_daily": None}}
weather_subscribers = set() # Tập hợp những người đăng ký nhận thời tiết

def get_user(psid):
    if psid not in users_db:
        users_db[psid] = {"balance": 1000, "last_daily": None}
    return users_db[psid]

# --- GAME TÀI XỈU ---
def play_taixiu(psid, bet_amount, choice):
    user = get_user(psid)
    if bet_amount > user["balance"]:
        return f"❌ M nghèo quá, chỉ có {user['balance']} điểm. Gõ /daily để nhận thêm!"
    if bet_amount <= 0:
        return "❌ Cược ít nhất 1 điểm."

    d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
    total = d1 + d2 + d3
    
    if d1 == d2 == d3:
        result = "BÃO"
    elif 4 <= total <= 10:
        result = "XỈU"
    else:
        result = "TÀI"

    text = f"🎲 Xúc xắc: {d1} - {d2} - {d3}\nTổng: {total} => **{result}**\n\n"

    if result == "BÃO":
        user["balance"] -= bet_amount
        text += f"💥 Ra bão! Nhà cái ăn hết. Mất {bet_amount} điểm.\n"
    elif result == choice.upper():
        user["balance"] += bet_amount
        text += f"🎉 M thắng! Lời {bet_amount} điểm.\n"
    else:
        user["balance"] -= bet_amount
        text += f"💸 M thua! Mất {bet_amount} điểm.\n"

    text += f"💰 Số dư: {user['balance']} điểm."
    return text

# --- GAME XÓC ĐĨA ---
def play_xocdia(psid, bet_amount, choice):
    user = get_user(psid)
    if bet_amount > user["balance"]:
        return f"❌ M nghèo quá, chỉ có {user['balance']} điểm. Gõ /daily để nhận thêm!"
    if bet_amount <= 0:
        return "❌ Cược ít nhất 1 điểm."

    # 1 = Trắng, 0 = Đen
    coins = [random.choice([0, 1]) for _ in range(4)]
    total = sum(coins)
    result = "CHẴN" if total % 2 == 0 else "LẺ"
    
    coins_str = " ".join(["⚪" if c == 1 else "⚫" for c in coins])
    text = f"🥣 Xóc đĩa: {coins_str}\nKết quả: **{result}**\n\n"

    if result == choice.upper():
        user["balance"] += bet_amount
        text += f"🎉 M thắng! Lời {bet_amount} điểm.\n"
    else:
        user["balance"] -= bet_amount
        text += f"💸 M thua! Mất {bet_amount} điểm.\n"

    text += f"💰 Số dư: {user['balance']} điểm."
    return text

# --- NHẬN ĐIỂM HÀNG NGÀY ---
def claim_daily(psid):
    user = get_user(psid)
    today = datetime.now().strftime("%Y-%m-%d")
    if user["last_daily"] == today:
        return "⏳ Hôm nay m nhận rồi, mai quay lại nhé!"
    user["balance"] += 1000
    user["last_daily"] = today
    return f"🎁 Nhận thành công 1000 điểm!\n💰 Số dư: {user['balance']} điểm."

# --- THỜI TIẾT HÀ NỘI ---
def get_weather_hn():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=21.0285&longitude=105.8542&current=temperature_2m,relative_humidity_2m,weather_code&timezone=Asia%2FHo_Chi_Minh"
        r = requests.get(url).json()
        current = r["current"]
        temp = current["temperature_2m"]
        hum = current["relative_humidity_2m"]
        code = current["weather_code"]
        
        if code == 0: desc = "Trời quang ☀️"
        elif code in [1, 2, 3]: desc = "Có mây ⛅"
        elif code in [45, 48]: desc = "Sương mù 🌫️"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: desc = "Mưa 🌧️"
        elif code in [95, 96, 99]: desc = "Dông ⛈️"
        else: desc = "Thời tiết khó đoán 🌤️"

        return f"🌤️ **Thời tiết Hà Nội hôm nay:**\n- Nhiệt độ: {temp}°C\n- Độ ẩm: {hum}%\n- Trạng thái: {desc}"
    except Exception as e:
        print("Lỗi lấy thời tiết:", e)
        return "❌ Không lấy được dữ liệu thời tiết."

def send_daily_weather():
    print("Đang gửi thông báo thời tiết...")
    msg = get_weather_hn()
    for psid in weather_subscribers:
        send_message(psid, msg)

# --- BACKGROUND SCHEDULER ---
def run_scheduler():
    # 00:00 UTC = 07:00 sáng giờ VN
    schedule.every().day.at("00:00").do(send_daily_weather)
    while True:
        schedule.run_pending()
        time.sleep(60)

# --- XỬ LÝ TIN NHẮN ---
def handle_message(psid, text):
    text = text.strip().lower()
    args = text.split()
    if not text: return

    if text in ["/start", "help", "menu"]:
        reply = (
            "🤖 **MENU BOT** 🤖\n"
            "/daily - Nhận 1000 điểm hàng ngày\n"
            "/taixiu <tiền> <tai/xiu> - Chơi tài xỉu\n"
            "/xocdia <tiền> <chan/le> - Chơi xóc đĩa\n"
            "/thoitiet - Bật/tắt nhận thời tiết Hà Nội (7h sáng)\n"
            "/sodu - Xem số dư"
        )
    elif text == "/sodu":
        user = get_user(psid)
        reply = f"💰 Số dư của m: {user['balance']} điểm."
    elif text == "/daily":
        reply = claim_daily(psid)
    elif text == "/thoitiet":
        if psid in weather_subscribers:
            weather_subscribers.remove(psid)
            reply = "🔕 Đã tắt thông báo thời tiết hàng ngày."
        else:
            weather_subscribers.add(psid)
            reply = "🔔 Đã bật thông báo thời tiết Hà Nội vào 7h sáng hàng ngày!"
    elif text.startswith("/taixiu"):
        if len(args) != 3:
            reply = "❌ Cú pháp: /taixiu <tiền> <tai/xiu>\nVí dụ: /taixiu 100 tai"
        else:
            try:
                bet = int(args[1])
                choice = args[2]
                if choice not in ["tai", "xiu"]:
                    reply = "❌ Chọn 'tai' hoặc 'xiu'."
                else:
                    reply = play_taixiu(psid, bet, choice)
            except ValueError:
                reply = "❌ Tiền cược phải là số."
    elif text.startswith("/xocdia"):
        if len(args) != 3:
            reply = "❌ Cú pháp: /xocdia <tiền> <chan/le>\nVí dụ: /xocdia 100 chan"
        else:
            try:
                bet = int(args[1])
                choice = args[2]
                if choice not in ["chan", "le"]:
                    reply = "❌ Chọn 'chan' hoặc 'le'."
                else:
                    reply = play_xocdia(psid, bet, choice)
            except ValueError:
                reply = "❌ Tiền cược phải là số."
    else:
        reply = "🤔 Lệnh không hợp lệ. Gõ 'help' để xem menu."

    send_message(psid, reply)

# --- FLASK WEBHOOK ---
@app.route('/', methods=['GET'])
def home():
    return "bot is alive", 200

@app.route('/webhook', methods=['GET'])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                if messaging_event.get("message") and not messaging_event["message"].get("is_echo"):
                    sender_id = messaging_event["sender"]["id"]
                    msg_text = messaging_event["message"].get("text", "")
                    if msg_text:
                        threading.Thread(target=handle_message, args=(sender_id, msg_text)).start()
    return "EVENT_RECEIVED", 200

def send_message(psid, text):
    payload = {"recipient": {"id": psid}, "message": {"text": text}}
    try:
        requests.post(GRAPH_URL, params={"access_token": PAGE_TOKEN}, json=payload)
    except Exception as e:
        print(f"Lỗi gửi tin nhắn tới {psid}: {e}")

# Khởi động background thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
