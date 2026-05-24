import feedparser
import requests
import os
import json
from datetime import datetime, timedelta, timezone

from groq import Groq
from bs4 import BeautifulSoup

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

DISCORD_BLUE = 0x5865F2

RSS_SOURCES = [
    # 新技術・グローバル
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    # ロボティクス
    {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    # 日本のAI動向
    {"name": "ITmedia AI+", "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
    {"name": "Zenn AI", "url": "https://zenn.dev/topics/ai/feed"},
]

MAX_PER_SOURCE = 5


def fetch_articles(source: dict) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
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

    prompt = f"""以下はAI関連ニュース記事の一覧です。

{articles_text}

以下の5つのカテゴリを意識しながら、合計10記事を選んでください。
カテゴリに偏りが出ないよう、その日の記事の中からバランスよく選んでください。
該当記事がないカテゴリは無理に埋めなくて構いません。

【選定カテゴリ】
1. AIの新技術（新モデル・新手法・研究成果など）
2. 日本のAI動向（国内企業・政策・導入事例など）
3. ロボティクス技術（AI×ロボット・自動化など）
4. AIツールの活用（Claude・NotebookLM・ChatGPTなどでできること）
5. 公的機関からのAI情報（政府・研究機関・国際機関の発表など）

選んだ記事は以下のJSON形式のみで返してください。余計な説明は不要です。日本語のみで記述してください。

{{
  "intro": "本日のAIニュース全体のトレンドを3〜4文で説明",
  "articles": [
    {{
      "title": "日本語タイトル（わかりやすく意訳してよい）",
      "url": "元のURL（変更しない）",
      "source": "ソース名",
      "category": "上記カテゴリ1〜5のいずれか",
      "summary": "記事の内容を3文で要約（日本語）",
      "importance": "なぜ重要か・何が新しいかを1文で"
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
        raise EnvironmentError("必要な環境変数が設定されていません（DISCORD_TOKEN / DISCORD_CHANNEL_ID / GROQ_API_KEY）")

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

    # ヘッダーメッセージ（メンション付き）
    send_embed({
        "content": "<@1245318763163947059>",
        "allowed_mentions": {"users": ["1245318763163947059"]},
        "embeds": [{
            "title": f"📰 {today_str}のAIニュース",
            "description": report_data["intro"],
            "color": DISCORD_BLUE,
            "footer": {"text": f"全{len(report_data['articles'])}記事をピックアップ"},
        }]
    })

    # 記事ごとのEmbed
    for i, article in enumerate(report_data["articles"], 1):
        print(f"  [{i}/{len(report_data['articles'])}] {article['title'][:30]}...")

        image_url = fetch_og_image_url(article["url"])

        category = article.get("category", "")
        article_url = article.get("url", "")
        embed = {
            "title": f"#{i:02d}  {article['title']}",
            "description": f"💡 {article['importance']}\n\n{article['summary']}",
            "color": DISCORD_BLUE,
            "footer": {"text": f"{article['source']}　|　{category}"},
        }
        if article_url.startswith("http://") or article_url.startswith("https://"):
            embed["url"] = article_url

        if image_url:
            embed["image"] = {"url": image_url}

        send_embed({"embeds": [embed]})

    print("完了")


if __name__ == "__main__":
    main()
