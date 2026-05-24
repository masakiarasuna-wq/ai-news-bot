import requests
import os
import json
import time
from datetime import datetime

from groq import Groq

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

COLOR = 0xF4A261  # オレンジ

SOURCES = """
【参照してよい信頼性の高い書籍・資料】
- "Artificial Intelligence: A Modern Approach" (Russell & Norvig)
- "Deep Learning" (Goodfellow, Bengio, Courville)
- "The Hundred-Page Machine Learning Book" (Andriy Burkov)
- "Human Compatible" (Stuart Russell)
- "Atlas of AI" (Kate Crawford)
- Stanford大学 CS229講義資料
- Google Machine Learning Crash Course
- OpenAI・Google・Meta等の公式研究論文・ブログ
"""

TOPICS = """
【扱ってよいテーマ例】
- 機械学習の基礎概念（教師あり/なし学習、過学習、バイアスと分散など）
- ニューラルネットワークとディープラーニングの仕組み
- 大規模言語モデル（LLM）の原理（Transformer、Attention機構など）
- プロンプトエンジニアリングの考え方
- AIの倫理・バイアス・ハルシネーション
- RAG（Retrieval-Augmented Generation）とは
- AIエージェントの概念
- 強化学習の基礎
"""


def generate_knowledge(today_str: str) -> dict:
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""あなたはAIの専門家です。今日（{today_str}）のAI基礎知識レッスンとして、5つのトピックを選んで解説してください。

{SOURCES}

{TOPICS}

以下のルール厳守：
- 必ず上記の信頼性の高い書籍・資料に基づいた内容にすること
- 誤った情報・推測は絶対に含めないこと
- 初心者でも理解できる平易な日本語で書くこと
- 毎回異なるトピックを選ぶこと（今日の日付を参考にバリエーションをもたせる）

以下のJSON形式のみで返してください：

{{
  "intro": "今日のAI基礎知識レッスンの概要を1〜2文で",
  "items": [
    {{
      "concept": "概念・用語名（日本語）",
      "explanation": "3〜4文でわかりやすく解説",
      "source": "参照した書籍名または資料名",
      "category": "基礎概念 or フレームワーク or 倫理・社会"
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

    print("AI基礎知識を生成中...")
    data = generate_knowledge(today_str)

    print("Discordに送信中...")

    send_embed({
        "content": "<@1245318763163947059>",
        "allowed_mentions": {"users": ["1245318763163947059"]},
        "embeds": [{
            "title": f"🧠 {today_str}のAI基礎知識",
            "description": data["intro"],
            "color": COLOR,
            "footer": {"text": "信頼性の高い書籍・資料に基づいた解説です"},
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
