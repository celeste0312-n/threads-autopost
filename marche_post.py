"""「マルシェ主催の教科書」の Instagram に、作っておいたカルーセル投稿を日付どおりに投稿する。

marche/posts.json に並んだ投稿のうち、今日（日本時間）の日付のものを1つ投稿する。
画像は marche/images/<番号>/ にある JPEG を、このコミットの公開URLから Instagram に渡す。
  python marche_post.py          … 今日の分があれば投稿する
  python marche_post.py --no 3   … 番号を指定して投稿する（日付は見ない）
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import instagram_api

JST = timezone(timedelta(hours=9))
HERE = Path(__file__).parent
DATA_DIR = HERE / "marche"
POSTS_FILE = DATA_DIR / "posts.json"
POSTED_FILE = DATA_DIR / "posted.txt"
CAPTION_MAX = 2200  # Instagram のキャプション上限
# ハッシュタグの上限が少なくなったという報道があるため、先頭から決まった数だけ使う
MAX_HASHTAGS = int(os.environ.get("MARCHE_MAX_HASHTAGS", "5"))


def wait_until_public(urls: list[str]) -> None:
    """画像がインターネットから見られるようになるまで待つ。"""
    for url in urls:
        for _ in range(20):
            if requests.head(url, timeout=30, allow_redirects=True).status_code == 200:
                break
            time.sleep(6)
        else:
            raise SystemExit(f"画像が公開されていません: {url}")


def posted_numbers() -> set[int]:
    if not POSTED_FILE.exists():
        return set()
    return {int(line.split()[0]) for line in POSTED_FILE.read_text().splitlines() if line.strip()}


def build_caption(post: dict) -> str:
    tags = " ".join(post["hashtags"][:MAX_HASHTAGS])
    return (post["caption"].strip() + "\n.\n.\n" + tags)[:CAPTION_MAX]


def pick(posts: list[dict], forced: int | None) -> dict | None:
    if forced is not None:
        return next((p for p in posts if p["no"] == forced), None)
    today = datetime.now(JST).strftime("%Y-%m-%d")
    return next((p for p in posts if p["date"] == today), None)


def main() -> None:
    forced = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--no" else None
    if not os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        print("MARCHE_INSTAGRAM_ACCESS_TOKEN がまだ登録されていないので、何もしません")
        return

    posts = json.loads(POSTS_FILE.read_text())
    post = pick(posts, forced)
    if post is None:
        print("今日投稿する分はありません")
        return
    if post["no"] in posted_numbers() and forced is None:
        print(f"No.{post['no']} はもう投稿済みです")
        return

    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    folder = f"marche/images/{post['no']:02d}"
    urls = [f"https://raw.githubusercontent.com/{repo}/{sha}/{folder}/{name}" for name in post["images"]]
    wait_until_public(urls)

    media_id = instagram_api.publish_carousel(urls, build_caption(post))
    print(f"No.{post['no']}「{post['title']}」を投稿しました:", media_id)

    now = datetime.now(JST)
    with POSTED_FILE.open("a") as f:
        f.write(f"{post['no']} {now:%Y-%m-%d %H:%M} {media_id} {post['title']}\n")


if __name__ == "__main__":
    main()
