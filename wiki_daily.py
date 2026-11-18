import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SEND_HOUR = int(os.environ.get("SEND_HOUR", "8"))      # IST me ghanta
SEND_MINUTE = int(os.environ.get("SEND_MINUTE", "0"))  # IST me minute

TG = f"https://api.telegram.org/bot{TOKEN}"
WIKI = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "StoryVideoBot/1.0 (your_email@example.com)"}  # apna asli email
IST = timezone(timedelta(hours=5, minutes=30))

KEYWORDS = [
    "unsolved mystery", "lost city", "ancient civilization mystery",
    "historical biography", "missing person case", "forgotten king",
    "famous disappearance", "historical betrayal", "ancient curse legend",
]

last_sent_date = None


def get_topics(keyword, want=10):
    items = []
    for offset in (random.randint(0, 100), 0):
        params = {
            "action": "query", "format": "json",
            "generator": "search", "gsrsearch": keyword,
            "gsrlimit": 15, "gsroffset": offset,
            "prop": "extracts|info", "exintro": 1, "explaintext": 1,
            "exsentences": 2, "exlimit": 15, "inprop": "url",
        }
        r = requests.get(WIKI, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        items = sorted(pages.values(), key=lambda p: p.get("index", 0))
        items = [p for p in items if not p["title"].startswith("List of")]
        if len(items) >= want:
            return items[:want]
    return items


def send(text):
    r = requests.post(f"{TG}/sendMessage", json={
        "chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True,
    }, timeout=30)
    r.raise_for_status()


def send_daily_topics():
    keyword = random.choice(KEYWORDS)
    topics = get_topics(keyword)
    send(f"🔎 Aaj ke 10 topics ({keyword}):")
    for i, p in enumerate(topics, 1):
        info = (p.get("extract") or "").strip()[:400]
        send(f"{i}. {p['title']}\n\n{info}\n\n{p['fullurl']}")
        time.sleep(0.5)


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

    def log_message(self, *args):   # har ping ka log band
        pass


if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Server port {port} par chalu hai")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
