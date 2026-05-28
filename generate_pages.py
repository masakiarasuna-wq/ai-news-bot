import feedparser
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from groq import Groq
from bs4 import BeautifulSoup

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_IDS = [
    os.environ.get("DISCORD_CHANNEL_ID"),
    os.environ.get("MARKETING_CHANNEL_ID"),
    os.environ.get("MARKETING_RESEARCH_CHANNEL_ID"),
]
PAGES_URL = "https://masakiarasuna-wq.github.io/ai-news-bot/"

# ===== RSS取得 =====

def fetch_articles(sources, days=30, max_per_source=3):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_articles = []
    for source in sources:
        try:
            feed = feedparser.parse(source["url"])
            count = 0
            for entry in feed.entries:
                parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
                if not parsed_time:
                    continue
                pub_dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
                if pub_dt >= cutoff and count < max_per_source:
                    all_articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": source["name"],
                        "summary": entry.get("summary", "")[:300],
                    })
                    count += 1
        except Exception:
            continue
    return all_articles


def fetch_og_image_url(url):
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        if tag and tag.get("content"):
            return tag["content"]
    except Exception:
        pass
    return None


# ===== Groqで要約・知識生成 =====

def call_groq(prompt, retries=3):
    client = Groq(api_key=GROQ_API_KEY)
    for attempt in range(retries):
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        text = completion.choices[0].message.content
        start = text.find("{")
        end = text.rfind("}") + 1
        try:
            return json.loads(text[start:end], strict=False)
        except json.JSONDecodeError:
            if attempt < retries - 1:
                print(f"  JSON解析失敗、リトライ中... ({attempt + 1}/{retries})")
                time.sleep(5)
            else:
                raise


def summarize_news(articles, topic, categories, exclude_ai=False):
    articles_text = "\n".join(
        f"{i}. [{a['source']}] {a['title']}\nURL: {a['url']}\n概要: {a['summary']}\n"
        for i, a in enumerate(articles, 1)
    )
    exclude = "【重要】AIツール・AI技術に関する記事は除いてください。\n" if exclude_ai else ""
    prompt = f"""以下は{topic}関連ニュース記事の一覧です。

{articles_text}

{exclude}これらから最も重要・参考になる5記事を選び、以下のJSON形式のみで返してください。日本語のみで記述してください。

{{
  "intro": "{topic}の最近のトレンドを2文で説明",
  "articles": [
    {{
      "title": "日本語タイトル",
      "url": "元のURL（変更しない）",
      "source": "ソース名",
      "summary": "3文で要約（日本語）",
      "importance": "重要な理由を1文で"
    }}
  ]
}}"""
    return call_groq(prompt)


def generate_knowledge(topic, sources_text, topics_text, today_str):
    prompt = f"""あなたは{topic}の専門家です。今日（{today_str}）の基礎知識レッスンとして5つのトピックを選んで解説してください。

{sources_text}

{topics_text}

ルール：信頼性の高い書籍に基づくこと。誤情報は含めないこと。AIツールの話題は除くこと。初心者向けの日本語で書くこと。

以下のJSON形式のみで返してください：

{{
  "intro": "今日の{topic}基礎知識レッスンの概要を1文で",
  "items": [
    {{
      "concept": "概念・用語名",
      "explanation": "3文でわかりやすく解説",
      "source": "参照した書籍名と著者名",
      "category": "カテゴリ"
    }}
  ]
}}"""
    return call_groq(prompt)


# ===== HTML生成 =====

def news_card_html(article, image_url, index, color):
    img_html = f'<img src="{image_url}" alt="" onerror="this.style.display=\'none\'">' if image_url else ""
    url = article.get("url", "")
    link_html = f'<a href="{url}" target="_blank" class="read-more">記事を読む →</a>' if url.startswith("http") else ""
    return f"""
<div class="card news-card">
  {img_html}
  <div class="card-body">
    <div class="card-num" style="color:{color}">#{index:02d}</div>
    <div class="card-title">{article['title']}</div>
    <div class="card-source">{article['source']}</div>
    <div class="card-importance">💡 {article['importance']}</div>
    <div class="card-text">{article['summary']}</div>
    {link_html}
  </div>
</div>"""


def knowledge_card_html(item, index, color):
    return f"""
<div class="card knowledge-card">
  <div class="card-body">
    <div class="card-num" style="color:{color}">#{index:02d}</div>
    <div class="card-title">{item['concept']}</div>
    <div class="card-category">{item['category']}</div>
    <div class="card-text">{item['explanation']}</div>
    <div class="card-source-badge">📖 {item['source']}</div>
  </div>
</div>"""


def build_html(sections, today_str):
    tabs = ""
    contents = ""
    for i, s in enumerate(sections):
        active = "active" if i == 0 else ""
        tabs += f'<button class="tab {active}" onclick="showTab({i})" style="--c:{s["color"]}">{s["icon"]} {s["label"]}</button>'

        news_cards = ""
        for j, (article, img) in enumerate(zip(s["news"]["articles"], s["news_images"]), 1):
            news_cards += news_card_html(article, img, j, s["color"])

        know_cards = ""
        for j, item in enumerate(s["knowledge"]["items"], 1):
            know_cards += knowledge_card_html(item, j, s["color"])

        display = "block" if i == 0 else "none"
        contents += f"""
<div class="tab-content" id="tab-{i}" style="display:{display}">
  <div class="section-intro" style="border-left:4px solid {s['color']}">{s['news']['intro']}</div>
  <h3 class="section-heading" style="color:{s['color']}">📰 ニュース</h3>
  <div class="card-grid">{news_cards}</div>
  <h3 class="section-heading" style="color:{s['color']}">📚 基礎知識</h3>
  <div class="section-intro" style="border-left:4px solid {s['color']}">{s['knowledge']['intro']}</div>
  <div class="card-grid">{know_cards}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Intelligence — {today_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f6fa; color: #222; }}
  header {{ background: #1a1a2e; color: #fff; padding: 24px 20px 16px; text-align: center; }}
  header h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: 0.05em; }}
  header p {{ font-size: 0.9rem; color: #aab; margin-top: 4px; }}
  .tabs {{ display: flex; gap: 8px; padding: 16px 20px 0; background: #fff; border-bottom: 1px solid #eee; flex-wrap: wrap; }}
  .tab {{ padding: 10px 18px; border: none; border-radius: 8px 8px 0 0; background: #f0f0f0; cursor: pointer; font-size: 0.9rem; font-weight: 600; transition: all 0.2s; }}
  .tab.active {{ background: var(--c); color: #fff; }}
  .tab:hover:not(.active) {{ background: #e0e0e0; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 20px; }}
  .section-intro {{ background: #fff; border-radius: 8px; padding: 14px 16px; margin-bottom: 20px; font-size: 0.95rem; line-height: 1.7; color: #444; }}
  .section-heading {{ font-size: 1.1rem; font-weight: 700; margin: 28px 0 12px; }}
  .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 16px; }}
  .card {{ background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.07); transition: transform 0.2s; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.12); }}
  .card img {{ width: 100%; height: 160px; object-fit: cover; display: block; }}
  .card-body {{ padding: 14px 16px; }}
  .card-num {{ font-size: 0.75rem; font-weight: 700; margin-bottom: 4px; }}
  .card-title {{ font-size: 0.95rem; font-weight: 700; line-height: 1.5; margin-bottom: 6px; color: #1a1a2e; }}
  .card-source {{ font-size: 0.75rem; color: #888; margin-bottom: 8px; }}
  .card-importance {{ font-size: 0.8rem; color: #555; background: #f8f8fc; border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; line-height: 1.5; }}
  .card-text {{ font-size: 0.85rem; color: #555; line-height: 1.7; margin-bottom: 10px; }}
  .read-more {{ font-size: 0.8rem; font-weight: 600; color: #5865F2; text-decoration: none; }}
  .read-more:hover {{ text-decoration: underline; }}
  .card-category {{ display: inline-block; font-size: 0.7rem; background: #eef; color: #668; border-radius: 4px; padding: 2px 8px; margin-bottom: 8px; }}
  .card-source-badge {{ font-size: 0.75rem; color: #888; margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f0f0; }}
  footer {{ text-align: center; padding: 24px; color: #aaa; font-size: 0.8rem; }}
  @media (max-width: 600px) {{ .card-grid {{ grid-template-columns: 1fr; }} header h1 {{ font-size: 1.3rem; }} }}
</style>
</head>
<body>
<header>
  <h1>📊 Daily Intelligence</h1>
  <p>{today_str} — AI・マーケティング・リサーチの最新情報</p>
</header>
<div class="tabs">{tabs}</div>
<main>{contents}</main>
<footer>自動生成 by GitHub Actions — 毎朝7時更新</footer>
<script>
function showTab(n) {{
  document.querySelectorAll('.tab-content').forEach((el,i) => el.style.display = i===n?'block':'none');
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active', i===n));
}}
</script>
</body>
</html>"""


# ===== メイン =====

def main():
    today = datetime.now()
    today_str = today.strftime("%Y年%m月%d日")
    print(f"=== {today_str} ページ生成開始 ===")

    # AI ニュース
    print("AI記事を取得中...")
    ai_sources = [
        {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
        {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
        {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
        {"name": "ITmedia AI+", "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
        {"name": "Zenn AI", "url": "https://zenn.dev/topics/ai/feed"},
    ]
    ai_articles = fetch_articles(ai_sources)
    print(f"  {len(ai_articles)}件取得")

    # マーケティング ニュース
    print("マーケティング記事を取得中...")
    mkt_sources = [
        {"name": "HubSpot Marketing", "url": "https://blog.hubspot.com/marketing/rss.xml"},
        {"name": "Content Marketing Institute", "url": "https://contentmarketinginstitute.com/feed/"},
        {"name": "MarTech", "url": "https://martech.org/feed/"},
        {"name": "Marketing Week", "url": "https://www.marketingweek.com/feed/"},
        {"name": "AdWeek", "url": "https://www.adweek.com/feed/"},
    ]
    mkt_articles = fetch_articles(mkt_sources)
    print(f"  {len(mkt_articles)}件取得")

    # リサーチ ニュース
    print("リサーチ記事を取得中...")
    res_sources = [
        {"name": "Research Live", "url": "https://www.research-live.com/rss"},
        {"name": "Harvard Business Review", "url": "https://feeds.hbr.org/harvardbusiness"},
        {"name": "Think with Google", "url": "https://www.thinkwithgoogle.com/rss/"},
        {"name": "MarketingProfs", "url": "https://www.marketingprofs.com/rss/articles.rss"},
    ]
    res_articles = fetch_articles(res_sources, days=90)
    print(f"  {len(res_articles)}件取得")

    # Groqで要約
    print("Groqで要約中...")
    ai_news = summarize_news(ai_articles, "AI", [])
    time.sleep(15)
    mkt_news = summarize_news(mkt_articles, "マーケティング", [], exclude_ai=True)
    time.sleep(15)
    res_news = summarize_news(res_articles, "マーケティングリサーチ", [], exclude_ai=True)
    time.sleep(15)

    # 基礎知識生成
    print("基礎知識を生成中...")
    ai_know = generate_knowledge("AI", """
参照書籍：Artificial Intelligence: A Modern Approach (Russell & Norvig), Deep Learning (Goodfellow et al.),
The Hundred-Page Machine Learning Book (Burkov), Human Compatible (Stuart Russell)""", """
テーマ例：機械学習の基礎、ニューラルネットワーク、LLMの仕組み、プロンプトエンジニアリング、AIの倫理""", today_str)
    time.sleep(15)
    mkt_know = generate_knowledge("マーケティング", """
参照書籍：Marketing Management (Kotler), Positioning (Al Ries & Jack Trout),
Building a StoryBrand (Donald Miller), Influence (Robert Cialdini), This Is Marketing (Seth Godin)""", """
テーマ例：STP分析、4P・4C、ブランドエクイティ、カスタマージャーニー、LTV、価格戦略""", today_str)
    time.sleep(15)
    res_know = generate_knowledge("マーケティングリサーチ", """
参照書籍：Marketing Research (Malhotra), Thinking Fast and Slow (Kahneman),
The Mom Test (Fitzpatrick), Predictably Irrational (Dan Ariely), How Brands Grow (Byron Sharp)""", """
テーマ例：定量・定性調査、サンプリング、質問票設計、インサイトの見つけ方、バイアスの種類""", today_str)
    time.sleep(15)

    # OG画像取得
    print("画像を取得中...")
    def get_images(articles):
        images = []
        for a in articles:
            images.append(fetch_og_image_url(a.get("url", "")))
            time.sleep(0.3)
        return images

    ai_images = get_images(ai_news["articles"])
    mkt_images = get_images(mkt_news["articles"])
    res_images = get_images(res_news["articles"])

    # HTML生成
    print("HTML生成中...")
    sections = [
        {"label": "AI", "icon": "🤖", "color": "#F4A261",
         "news": ai_news, "news_images": ai_images, "knowledge": ai_know},
        {"label": "マーケティング", "icon": "📣", "color": "#9B59B6",
         "news": mkt_news, "news_images": mkt_images, "knowledge": mkt_know},
        {"label": "リサーチ", "icon": "🔬", "color": "#1ABC9C",
         "news": res_news, "news_images": res_images, "knowledge": res_know},
    ]

    html = build_html(sections, today_str)

    Path("site").mkdir(exist_ok=True)
    Path("site/index.html").write_text(html, encoding="utf-8")
    print("完了 → site/index.html")

    # Discord通知
    if DISCORD_TOKEN:
        print("Discordに通知中...")
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "embeds": [{
                "title": f"📊 {today_str}のDaily Intelligenceが更新されました",
                "description": f"AI・マーケティング・リサーチの最新ニュースと基礎知識をまとめたレポートです。",
                "url": PAGES_URL,
                "color": 0x1a1a2e,
                "footer": {"text": "毎朝7時自動更新 | GitHub Pages"},
            }]
        }
        for channel_id in DISCORD_CHANNEL_IDS:
            if channel_id:
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                if not resp.ok:
                    print(f"[Discord エラー] {channel_id}: {resp.status_code}: {resp.text}")
                time.sleep(1.5)


if __name__ == "__main__":
    main()
