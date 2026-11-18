import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = str(os.environ["CHAT_ID"])
SEND_HOUR = int(os.environ.get("SEND_HOUR", "8"))      # IST me ghanta
SEND_MINUTE = int(os.environ.get("SEND_MINUTE", "0"))  # IST me minute
STARTUP_MSG = os.environ.get("STARTUP_MSG", "1") == "1"  # "0" kar do to start par hi nahi bolega

TG = f"https://api.telegram.org/bot{TOKEN}"
HEADERS = {"User-Agent": "StoryVideoBot/1.0 (your_email@example.com)"}  # apna asli email
IST = timezone(timedelta(hours=5, minutes=30))

LANGS = {
    "hi": {
        "api": "https://hi.wikipedia.org/w/api.php",
        "heading": "🇮🇳 हिंदी के 5 topics",
        "skip": ("सूची", "List of"),
        "keywords": [
            "रहस्य", "रहस्यमयी घटना", "खोया हुआ शहर", "प्राचीन सभ्यता",
            "ऐतिहासिक घटना", "जीवनी", "राजा का इतिहास", "विश्वासघात",
            "रहस्यमय मृत्यु", "लापता", "किला", "युद्ध का इतिहास",
        ],
    },
    "en": {
        "api": "https://en.wikipedia.org/w/api.php",
        "heading": "🌐 English topics (5)",
        "skip": ("List of",),
        "keywords": [
            "unsolved mystery", "lost city", "ancient civilization mystery",
            "historical biography", "missing person case", "forgotten king",
            "famous disappearance", "historical betrayal", "ancient curse legend",
        ],
    },
}

last_sent_date = None
sent_ids = {"hi": set(), "en": set()}   # restart par reset hota hai
send_lock = threading.Lock()            # ek time par ek hi batch jaye

HELP_TEXT = (
    "Hi! 👋 Main aapka Story Topic Bot hu.\n\n"
    "Commands:\n"
    "/new - abhi naye topics (5 Hindi + 5 English)\n"
    "/start - ye message dobara\n\n"
    f"Roz subah {SEND_HOUR:02d}:{SEND_MINUTE:02d} IST par topics apne aap aate hain."
)


def fetch(lang, keyword, offset):
    params = {
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": keyword,
        "gsrlimit": 15, "gsroffset": offset,
        "prop": "extracts|info", "exintro": 1, "explaintext": 1,
        "exsentences": 3, "exlimit": 15, "inprop": "url",
    }
    r = requests.get(LANGS[lang]["api"], params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    return sorted(pages.values(), key=lambda p: p.get("index", 0))


def get_topics(lang, want=5):
    cfg = LANGS[lang]
    keywords = cfg["keywords"][:]
    random.shuffle(keywords)
    picked = []
    for kw in keywords:
        for offset in (random.randint(0, 50), 0):
            try:
                items = fetch(lang, kw, offset)
            except Exception as e:
                print("Fetch error:", lang, kw, e)
                continue
            for p in items:
                title = p["title"]
                info = (p.get("extract") or "").strip()
                if title.startswith(cfg["skip"]) or "बहुविकल्पी" in title or "disambiguation" in title.lower():
                    continue
                if len(info) < 100:                       # bahut chhote stub pages chhodo
                    continue
                if p["pageid"] in sent_ids[lang] or any(p["pageid"] == x["pageid"] for x in picked):
                    continue
                picked.append(p)
                if len(picked) == want:
                    return picked
            if len(picked) >= want:
                return picked
    return picked


def send(text):
    r = requests.post(f"{TG}/sendMessage", json={
        "chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True,
    }, timeout=30)
    r.raise_for_status()


def send_daily_topics():
    with send_lock:
        for lang in ("hi", "en"):
            topics = get_topics(lang, 5)
            if not topics:
                send(f"{LANGS[lang]['heading']}: aaj kuch nahi mila.")
                continue
            send(f"{LANGS[lang]['heading']}")
            for i, p in enumerate(topics, 1):
                info = (p.get("extract") or "").strip()[:450]
                send(f"{i}. {p['title']}\n\n{info}\n\n{p['fullurl']}")
                sent_ids[lang].add(p["pageid"])
                time.sleep(0.5)


def handle_new():
    """/new command: naye topics bhejo (background thread me chalta hai)."""
    try:
        send_daily_topics()
    except Exception as e:
        print("handle_new error:", e)
        try:
            send("⚠️ Kuch gadbad ho gayi, thodi der baad /new try karo.")
        except Exception:
            pass


def handle_message(text):
    parts = text.strip().split()
    if not parts:
        return
    cmd = parts[0].split("@")[0].lower()   # /new@MyBot -> /new

    if cmd in ("/start", "/help", "hi", "hello", "hii", "namaste"):
        send(HELP_TEXT)
    elif cmd == "/new":
        if send_lock.locked():
            send("⏳ Abhi topics bhej raha hu, thoda ruko.")
        else:
            send("🔄 Naye topics la raha hu...")
            threading.Thread(target=handle_new, daemon=True).start()


def poll_updates():
    """Telegram se messages sunta hai (long polling)."""
    # agar kabhi webhook set tha to getUpdates nahi chalega, isliye hata do
    try:
        requests.get(f"{TG}/deleteWebhook", timeout=15)
    except Exception as e:
        print("deleteWebhook error:", e)

    offset = None
    # bot band tha tab ke purane messages skip karo
    try:
        r = requests.get(f"{TG}/getUpdates", params={"offset": -1}, timeout=15).json()
        res = r.get("result", [])
        if res:
            offset = res[-1]["update_id"] + 1
    except Exception as e:
        print("initial getUpdates error:", e)

    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"{TG}/getUpdates", params=params, timeout=40)
            r.raise_for_status()
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = str(msg.get("chat", {}).get("id", ""))
                if chat != CHAT_ID:          # sirf aapki chat ka command chalega
                    continue
                handle_message(msg.get("text", ""))
        except Exception as e:
            print("Poll error:", e)
            time.sleep(5)


def scheduler():
    """Har 30 sec me check karta hai; din me sirf ek baar bhejta hai."""
    global last_sent_date
    while True:
        try:
            now = datetime.now(IST)
            due = now.replace(hour=SEND_HOUR, minute=SEND_MINUTE, second=0, microsecond=0)
            in_window = timedelta(0) <= now - due < timedelta(minutes=30)
            if in_window and last_sent_date != now.date():
                last_sent_date = now.date()      # pehle mark, taaki double na jaye
                print("Sending daily topics...", now)
                send_daily_topics()
        except Exception as e:
            print("Error:", e)
        time.sleep(30)


class Handler(BaseHTTPRequestHandler):
    def _ok(self):
        body = f"OK {datetime.now(IST):%Y-%m-%d %H:%M:%S} IST".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return body

    def do_GET(self):
        self.wfile.write(self._ok())

    def do_HEAD(self):
        self._ok()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if STARTUP_MSG:
        try:
            send("Hi! 👋 Bot chalu ho gaya.\n\nNaye topics ke liye /new bhejo.")
        except Exception as e:
            print("Startup msg error:", e)

    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=poll_updates, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Server port {port} par chalu hai")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
