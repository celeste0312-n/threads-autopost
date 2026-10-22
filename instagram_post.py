"""Instagram にスライド（カルーセル）投稿を自動で行う。

GitHub Actions から2段階で呼ばれる。
  python instagram_post.py generate  … Gemini で内容を作り、スライド画像を ig_images/ に保存する
  （ここで画像をリポジトリに push して、インターネットから見られる状態にする）
  python instagram_post.py publish   … 公開された画像を Instagram に投稿し、記録して画像を片付ける
"""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import gemini
import instagram_api
import slides

JST = timezone(timedelta(hours=9))
HERE = Path(__file__).parent
IMAGES_DIR = HERE / "ig_images"
PENDING_FILE = IMAGES_DIR / "pending.json"
POSTED_FILE = HERE / "ig_posted.txt"
HANDLE = os.environ.get("INSTAGRAM_HANDLE", "@celeste_live")
CAPTION_MAX = 2200  # Instagram のキャプション上限

FORMAT = """次の形の JSON だけを出力してください（説明やコードブロックは不要）。
{
  "hook": "表紙の一言（25文字以内）",
  "sub": "表紙の補足（25文字以内）",
  "slides": [
    {"heading": "見出し（14文字以内）", "body": "本文（80文字以内）"}
  ],
  "closing_heading": "最後のスライドの見出し（12文字以内）",
  "closing_body": "最後のスライドの本文（50文字以内）",
  "caption": "キャプション本文（ハッシュタグは含めない。400文字以内）",
  "hashtags": ["#celeste", "#ライバー事務所"]
}
slides は3〜5個。hashtags は5〜10個。スライドの文字（hook / sub / slides / closing）には絵文字を使わない。"""


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON が見つかりません")
    post = json.loads(m.group(0))
    if not (3 <= len(post["slides"]) <= 5):
        raise ValueError("スライドの枚数が範囲外です")
    for key in ("hook", "closing_heading", "closing_body", "caption"):
        if not str(post.get(key, "")).strip():
            raise ValueError(f"{key} が空です")
    for s in post["slides"]:
        if not s.get("heading") or not s.get("body"):
            raise ValueError("スライドの見出しか本文が空です")
    return post


def build_caption(post: dict) -> str:
    tags = []
    for t in post.get("hashtags", [])[:10]:
        t = "#" + str(t).lstrip("#＃").strip()
        if len(t) > 1 and t not in tags:
            tags.append(t)
    caption = post["caption"].strip() + "\n.\n.\n" + " ".join(tags)
    return caption[:CAPTION_MAX]


def generate() -> None:
    now = datetime.now(JST)
    persona = (HERE / "ig_persona.md").read_text()
    try:
        recent = instagram_api.recent_captions()
    except RuntimeError as e:
        print("最近の投稿を取得できませんでした:", e)
        recent = []
    recent_list = "\n".join(f"- {c[:120]}" for c in recent) or "（まだありません）"
    prompt = (
        f"今は日本時間で{now:%Y年%m月%d日}です。Instagram のカルーセル投稿を1つ作ってください。\n\n"
        f"最近の投稿（テーマや表紙の言い回しが重ならないようにしてください）:\n{recent_list}\n\n{FORMAT}"
    )
    last_error = None
    for _ in range(3):
        try:
            post = parse_json(gemini.generate(persona, prompt))
            break
        except (ValueError, KeyError, TypeError) as e:
            last_error = e
            print("AI の出力の形が正しくなかったため、作り直します:", e)
    else:
        raise SystemExit(f"投稿の内容を作れませんでした: {last_error}")

    if IMAGES_DIR.exists():
        shutil.rmtree(IMAGES_DIR)
    paths = slides.render(post, HANDLE, IMAGES_DIR)
    caption = build_caption(post)
    PENDING_FILE.write_text(
        json.dumps({"images": [p.name for p in paths], "caption": caption}, ensure_ascii=False, indent=2)
    )
    print(f"スライド{len(paths)}枚を作りました。\n--- キャプション ---\n{caption}\n---")


def wait_until_public(urls: list[str]) -> None:
    """push した画像が、インターネットから見られるようになるまで待つ。"""
    for url in urls:
        for _ in range(20):
            if requests.head(url, timeout=30, allow_redirects=True).status_code == 200:
                break
            time.sleep(6)
        else:
            raise SystemExit(f"画像が公開されませんでした（リポジトリが公開になっているか確認してください）: {url}")


def publish() -> None:
    if not PENDING_FILE.exists():
        raise SystemExit("投稿する画像がありません。先に generate を実行してください")
    pending = json.loads(PENDING_FILE.read_text())
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["IMAGES_COMMIT"]  # 画像を push したコミット。URL を固定して古い画像が出ないようにする
    urls = [f"https://raw.githubusercontent.com/{repo}/{sha}/ig_images/{name}" for name in pending["images"]]
    wait_until_public(urls)

    media_id = instagram_api.publish_carousel(urls, pending["caption"])
    print("Instagram に投稿しました:", media_id)

    now = datetime.now(JST)
    with POSTED_FILE.open("a") as f:
        f.write(f"# {now:%Y-%m-%d %H:%M}（スライド{len(urls)}枚）\n{pending['caption']}\n---\n")
    shutil.rmtree(IMAGES_DIR)  # Instagram 側に保存されたので、リポジトリの画像は片付ける


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "generate":
        generate()
    elif command == "publish":
        publish()
    else:
        raise SystemExit("使い方: python instagram_post.py generate|publish")
