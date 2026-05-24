import requests
import os
import json
import time
from datetime import datetime

from groq import Groq

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("MARKETING_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

COLOR = 0x9B59B6  # パープル

SOURCES = """
【参照してよい信頼性の高い書籍・資料】
- "Kotler on Marketing" / "Marketing Management" (Philip Kotler)
- "Positioning: The Battle for Your Mind" (Al Ries & Jack Trout)
- "Building a StoryBrand" (Donald Miller)
- "Influence: The Psychology of Persuasion" (Robert Cialdini)
- "Hooked: How to Build Habit-Forming Products" (Nir Eyal)
- "This Is Marketing" (Seth Godin)
- "Contagious: Why Things Catch On" (Jonah Berger)
- "The 22 Immutable Laws of Marketing" (Al Ries & Jack Trout)
- "Blue Ocean Strategy" (W. Chan Kim & Renée Mauborgne)
- "Good to Great" (Jim Collins)
"""

TOPICS = """
【扱ってよいテーマ例】
- STP分析（セグメンテーション・ターゲティング・ポジショニング）
- 4P・4Cフレームワーク
- ブランドエクイティの概念
- カスタマージャーニーとタッチポイント
- コンテンツマーケティングの本質
- 顧客生涯価値（LTV）とロイヤルティ
- パーセプションマップの使い方
- 価格戦略の考え方
- 口コミ・バイラルマーケティングの原理
- ストーリーブランディング
"""


def generate_knowledge(today_str: str) -> dict:
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""あなたはマーケティングの専門家です。今日（{today_str}）のマーケティング基礎知識レッスンとして、5つのトピックを選んで解説してください。

{SOURCES}

{TOPICS}

以下のルール厳守：
- 必ず上記の信頼性の高い書籍に基づいた内容にすること
- 誤った情報・推測は絶対に含めないこと
- 初心者でも理解できる平易な日本語で書くこと
- AIツール・AI技術に関する話題は除くこと
- 毎回異なるトピックを選ぶこと（今日の日付を参考にバリエーションをもたせる）

以下のJSON形式のみで返してください：

{{
  "intro": "今日のマーケティング基礎知識レッスンの概要を1〜2文で",
  "items": [
    {{
      "concept": "概念・フレームワーク名（日本語）",
      "explanation": "3〜4文でわかりやすく解説",
      "source": "参照した書籍名と著者名",
      "category": "基礎概念 or フレームワーク or 戦略 or 消費者心理"
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
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if not resp.ok:
        print(f"[Discord エラー] {resp.status_code}: {resp.text}")
    resp.raise_for_status()


def main() -> None:
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID or not GROQ_API_KEY:
        raise EnvironmentError("必要な環境変数が設定されていません")

    today = datetime.now()
    today_str = today.strftime("%Y年%m月%d日")

    print("マーケティング基礎知識を生成中...")
    data = generate_knowledge(today_str)

    print("Discordに送信中...")

    send_embed({
        "content": "<@1245318763163947059>",
        "allowed_mentions": {"users": ["1245318763163947059"]},
        "embeds": [{
            "title": f"📚 {today_str}のマーケティング基礎知識",
            "description": data["intro"],
            "color": COLOR,
            "footer": {"text": "定評ある書籍に基づいた解説です"},
        }]
    })
    time.sleep(1.5)

    for i, item in enumerate(data["items"], 1):
        print(f"  [{i}/5] {item['concept']}")
        send_embed({"embeds": [{
            "title": f"#{i:02d}  {item['concept']}",
            "description": f"{item['explanation']}",
            "color": COLOR,
            "footer": {"text": f"出典: {item['source']}　|　{item['category']}"},
        }]})
        time.sleep(1.5)

    print("完了")


if __name__ == "__main__":
    main()
