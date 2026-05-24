import feedparser
import requests
import os
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")

RSS_SOURCES = [
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    },
    {
        "name": "Zenn AI",
        "url": "https://zenn.dev/topics/ai/feed",
        "lang": "ja",
    },
]

MAX_CHARS = 1900  # Discord limit is 2000; leaving buffer


def translate_to_japanese(text: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="ja").translate(text)
    except Exception:
        return text


def fetch_articles(source: dict) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    is_japanese = source.get("lang") == "ja"

    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        print(f"[ERROR] {source['name']} の取得に失敗: {e}")
        return []

    articles = []
    for entry in feed.entries:
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed_time:
            continue
        pub_dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
        if pub_dt >= cutoff:
            title = entry.get("title", "(タイトルなし)")
            if not is_japanese:
                title = translate_to_japanese(title)
            articles.append({"title": title, "url": entry.get("link", "")})

    return articles


def send_message(content: str) -> None:
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json={"content": content}, timeout=10)
    if not resp.ok:
        print(f"[Discord エラー] {resp.status_code}: {resp.text}")
    resp.raise_for_status()


def build_messages(sources_articles: list[tuple[str, list[dict]]], header: str) -> list[str]:
    messages = []
    current = header

    for source_name, articles in sources_articles:
        section_header = f"**{source_name}**（{len(articles)}件）\n"
        if len(current) + len(section_header) > MAX_CHARS:
            messages.append(current)
            current = section_header
        else:
            current += section_header

        for a in articles:
            line = f"• {a['title']}\n  {a['url']}\n"
            if len(current) + len(line) > MAX_CHARS:
                messages.append(current)
                current = line
            else:
                current += line

        current += "\n"

    if current.strip():
        messages.append(current)

    return messages


def main() -> None:
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        raise EnvironmentError("DISCORD_TOKEN または DISCORD_CHANNEL_ID が設定されていません")

    today = datetime.now().strftime("%Y年%m月%d日")
    header = f"📰 **{today}のAIニュース**\n\n"

    sources_articles = []
    total_count = 0

    for source in RSS_SOURCES:
        articles = fetch_articles(source)
        if not articles:
            continue
        total_count += len(articles)
        sources_articles.append((source["name"], articles))

    if total_count == 0:
        send_message(f"{header}本日は新着記事が見つかりませんでした。")
        print("新着記事なし")
        return

    messages = build_messages(sources_articles, header)
    for msg in messages:
        send_message(msg)

    print(f"送信完了: {total_count}件の記事を {len(messages)} メッセージで送信")


if __name__ == "__main__":
    main()
