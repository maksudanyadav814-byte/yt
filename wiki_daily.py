import os
import random
import time
import requests

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
TG = f"https://api.telegram.org/bot{TOKEN}"
WIKI = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "StoryVideoBot/1.0 (your_email@example.com)"}  # apna email

KEYWORDS = [
    "unsolved mystery", "lost city", "ancient civilization mystery",
    "historical biography", "missing person case", "forgotten king",
    "famous disappearance", "historical betrayal", "ancient curse legend",
]


def get_topics(keyword, want=10):
    for offset in (random.randint(0, 100), 0):   # random offset se roz naye topics
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


def main():
    keyword = random.choice(KEYWORDS)
    topics = get_topics(keyword)
    send(f"🔎 Aaj ke 10 topics ({keyword}):")
    for i, p in enumerate(topics, 1):
        info = (p.get("extract") or "").strip()[:400]
        send(f"{i}. {p['title']}\n\n{info}\n\n{p['fullurl']}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
