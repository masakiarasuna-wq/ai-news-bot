import feedparser
import requests
import os
import json
from datetime import datetime, timedelta, timezone

from groq import Groq
from bs4 import BeautifulSoup

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("MARKETING_RESEARCH_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

DISCORD_GREEN = 0x57F287  # リサーチ用：グリーン

RSS_SOURCES = [
    {"name": "Research Live", "url": "https://www.research-live.com/rss"},
    {"name": "Quirks Marketing Research", "url": "https://www.quirks.com/rss.aspx"},
    {"name": "GreenBook", "url": "https://www.greenbook.org/feed"},
    {"name": "Survey Sampling International", "url": "https://www.ssinternational.com/feed/"},
    {"name": "MarketingProfs", "url": "https://www.marketingprofs.com/rss/articles.rss"},
    {"name": "Harvard Business Review", "url": "https://hbr.org/section/marketing/feed"},
]

MAX_PER_SOURCE = 10


def fetch_articles(source: dict) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        feed = feedparser.parse(source["url"])
    except Exception:
        return []
    articles = []
    for entry in feed.entries:
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed_time:
            continue
        pub_dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
        if pub_dt >= cutoff:
            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": source["name"],
                "summary": entry.get("summary", "")[:600],
            })
    return articles[:MAX_PER_SOURCE]


def fetch_og_image_url(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = (
            soup.find("meta", property="og:image")
            or soup.find("meta", attrs={"name": "twitter:image"})
        )
        if tag and tag.get("content"):
            return tag["content"]
    except Exception:
        pass
    return None


def summarize_with_groq(articles: list[dict]) -> dict:
    client = Groq(api_key=GROQ_API_KEY)

    articles_text = "\n".join(
        f"{i}. [{a['source']}] {a['title']}\nURL: {a['url']}\n概要: {a['summary']}\n"
        for i, a in enumerate(articles, 1)
    )

    prompt = f"""以下は過去1ヶ月のマーケティングリサーチ関連ニュース記事の一覧です。

{articles_text}

これらから最も重要・参考になる5記事を選び、以下のJSON形式のみで返してください。
余計な説明は不要です。日本語のみで記述してください。

選定の観点：調査手法・消費者インサイト・データ分析・リサーチ業界の動向など

{{
  "intro": "今週のマーケティングリサーチトレンドを3文で説明",
  "articles": [
    {{
      "title": "日本語タイトル（わかりやすく意訳してよい）",
      "url": "元のURL（変更しない）",
      "source": "ソース名",
      "summary": "記事の内容を3文で要約（日本語）",
      "importance": "なぜ重要か・何が参考になるかを1文で"
    }}
  ]
}}"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    text = completion.choices[0].message.content
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end], strict=False)


def send_embed(payload: dict) -> None:
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if not resp.ok:
        print(f"[Discord エラー] {resp.status_code}: {resp.text}")
    resp.raise_for_status()


def main() -> None:
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID or not GROQ_API_KEY:
        raise EnvironmentError("必要な環境変数が設定されていません")

    today = datetime.now()
    today_str = today.strftime("%Y年%m月%d日")

    print("記事を取得中...")
    all_articles: list[dict] = []
    for source in RSS_SOURCES:
        arts = fetch_articles(source)
        print(f"  {source['name']}: {len(arts)}件")
        all_articles.extend(arts)

    if not all_articles:
        print("新着記事なし")
        return

    print(f"Groqで要約中（計{len(all_articles)}件）...")
    report_data = summarize_with_groq(all_articles)

    print("Discordに送信中...")

    send_embed({
        "content": "<@1245318763163947059>",
        "allowed_mentions": {"users": ["1245318763163947059"]},
        "embeds": [{
            "title": f"🔍 {today_str}のマーケティングリサーチニュース",
            "description": report_data["intro"],
            "color": DISCORD_GREEN,
            "footer": {"text": f"過去1ヶ月から{len(report_data['articles'])}記事をピックアップ"},
        }]
    })

    for i, article in enumerate(report_data["articles"], 1):
        print(f"  [{i}/{len(report_data['articles'])}] {article['title'][:30]}...")

        image_url = fetch_og_image_url(article["url"])

        embed = {
            "title": f"#{i:02d}  {article['title']}",
            "description": f"💡 {article['importance']}\n\n{article['summary']}",
            "color": DISCORD_GREEN,
            "footer": {"text": article["source"]},
        }

        article_url = article.get("url", "")
        if article_url.startswith("http://") or article_url.startswith("https://"):
            embed["url"] = article_url

        if image_url:
            embed["image"] = {"url": image_url}

        send_embed({"embeds": [embed]})

    print("完了")


if __name__ == "__main__":
    main()
