from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import threading
import sqlite3
import urllib.request
import os
from collections import deque

# ========== تنظیمات ==========
TOKEN = "400404882:JYKnasyJGd6y_4rEFeRyHGGZAvE72FlHWIg"
ADMIN_USERNAME = "whysay"
MAX_WAITING = 30
waiting_list = deque(maxlen=MAX_WAITING)
pairs = {}

# ========== وب سرور ساده برای Render ==========
PORT = int(os.environ.get("PORT", 8080))

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"MILI CHAT Bot is Running!")
    
    def log_message(self, format, *args):
        pass

def start_server():
    server = HTTPServer(('0.0.0.0', PORT), SimpleHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()
# ============================================

# ========== دیتابیس ==========
def db_execute(query, params=(), fetch_one=False, fetch_all=False):
    conn = sqlite3.connect('bot_data.db', timeout=10)
    c = conn.cursor()
    c.execute(query, params)
    if fetch_one:
        result = c.fetchone()
    elif fetch_all:
        result = c.fetchall()
    else:
        result = None
    conn.commit()
    conn.close()
    return result

def init_db():
    db_execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            last_seen INTEGER,
            username TEXT
        )
    ''')
init_db()

# ========== API بله ==========
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

def send_msg(chat_id, text, kb=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if kb:
        data["reply_markup"] = kb
    try:
        url = f"{BASE_URL}/sendMessage"
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except:
        return None

def edit_msg(chat_id, msg_id, text):
    try:
        url = f"{BASE_URL}/editMessageText"
        data = {"chat_id": chat_id, "message_id": msg_id, "text": text}
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except:
        return None

def answer_cb(cb_id):
    try:
        url = f"{BASE_URL}/answerCallbackQuery"
        data = {"callback_query_id": cb_id}
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except:
        pass

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates?timeout=25"
    if offset:
        url += f"&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            data = json.loads(res.read().decode())
            return data if data.get("ok") else {"result": []}
    except:
        return {"result": []}

# ========== کیبوردها ==========
KB_START = {"inline_keyboard": [[{"text": "🔎 شروع چت", "callback_data": "next"}]]}
KB_CHAT = {"inline_keyboard": [[{"text": "⏭️ پارتنر بعدی", "callback_data": "next"}], [{"text": "🛑 پایان چت", "callback_data": "stop"}]]}
KB_END = {"inline_keyboard": [[{"text": "🔎 شروع دوباره", "callback_data": "next"}], [{"text": "⚠️ گزارش کاربر", "callback_data": "report"}]]}

# ========== متن‌ها ==========
TXT = {
    "welcome": "🔰 MILI CHAT\n\n🔎 پیدا کردن پارتنر تصادفی\n\nبرای شروع کلیک کنید 👇",
    "search": "🔎 در حال جستجو...",
    "connect": "⚡️ متصل شد!\n🛡️ پارتنر پیدا شد",
    "end": "🛑 چت پایان یافت.\n\nبرای شروع مجدد کلیک کنید.",
    "left": "❌ پارتنر شما چت را ترک کرد.",
    "report": "✅ گزارش شما ثبت شد.",
    "nochat": "🔍 شما در چت نیستید.\nروی Start کلیک کنید.",
}

# ========== توابع ==========
def match():
    if len(waiting_list) >= 2:
        a = waiting_list.popleft()
        b = waiting_list.popleft()
        pairs[a] = b
        pairs[b] = a
        send_msg(a, TXT["connect"], KB_CHAT)
        send_msg(b, TXT["connect"], KB_CHAT)
        print(f"✅ جفت شد: {a[:8]}... <-> {b[:8]}...")

def handle(chat_id, text, msg_id, cb_id=None, username=""):
    db_execute("INSERT OR REPLACE INTO users (user_id, last_seen, username) VALUES (?, ?, ?)", 
               (chat_id, int(time.time()), username))
    
    if text == "/start":
        send_msg(chat_id, TXT["welcome"], KB_START)
        return
    
    if cb_id:
        answer_cb(cb_id)
        
        if text == "next":
            p = pairs.pop(chat_id, None)
            if p:
                pairs.pop(p, None)
                send_msg(p, TXT["left"], KB_START)
            if chat_id in waiting_list:
                waiting_list.remove(chat_id)
            edit_msg(chat_id, msg_id, TXT["search"])
            if chat_id not in waiting_list and chat_id not in pairs:
                waiting_list.append(chat_id)
            match()
        
        elif text == "stop":
            p = pairs.pop(chat_id, None)
            if p:
                pairs.pop(p, None)
                send_msg(p, TXT["left"], KB_START)
            if chat_id in waiting_list:
                waiting_list.remove(chat_id)
            send_msg(chat_id, TXT["end"], KB_START)
        
        elif text == "report":
            p = pairs.get(chat_id)
            if p:
                send_msg(chat_id, TXT["report"], KB_START)
                pairs.pop(chat_id, None)
                pairs.pop(p, None)
            else:
                send_msg(chat_id, "⚠️ هیچ پارتنری نیست", KB_START)
    
    elif chat_id in pairs:
        send_msg(pairs[chat_id], f"📝 {text}")
    else:
        if chat_id not in waiting_list:
            send_msg(chat_id, TXT["nochat"], KB_START)

# ========== حلقه اصلی ==========
print("=" * 50)
print("🤖 MILI CHAT Bot Started!")
print(f"👑 Admin: @{ADMIN_USERNAME}")
print(f"🌐 Web: http://localhost:{PORT}")
print("=" * 50)

last_id = 0

def matching_loop():
    while True:
        time.sleep(2)
        match()

threading.Thread(target=matching_loop, daemon=True).start()

while True:
    try:
        updates = get_updates(last_id + 1)
        if updates and updates.get("result"):
            for update in updates["result"]:
                last_id = update["update_id"]
                
                if "message" in update:
                    m = update["message"]
                    chat_id = str(m["chat"]["id"])
                    text = m.get("text", "")
                    msg_id = m["message_id"]
                    username = m.get("from", {}).get("username", "")
                    handle(chat_id, text, msg_id, username=username)
                
                elif "callback_query" in update:
                    c = update["callback_query"]
                    chat_id = str(c["from"]["id"])
                    data = c.get("data", "")
                    msg_id = c["message"]["message_id"]
                    cb_id = c["id"]
                    username = c.get("from", {}).get("username", "")
                    handle(chat_id, data, msg_id, cb_id, username)
    
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)
