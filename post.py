"""schedule.json の時間帯になっていたら Threads に投稿する。

posts.txt に投稿が書いてあればその先頭を、空なら Gemini（無料枠）で
persona.md に沿った文章を作って投稿する。

GitHub Actions から1時間おきに呼ばれる。実行が遅れても投稿を取りこぼさないよう、
「予定時刻から2時間以内」かつ「予定時刻以降にまだ投稿していない」ときに投稿する。
投稿した文章は posted.txt の末尾に記録する。
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gemini
import threads_api

JST = timezone(timedelta(hours=9))
HERE = Path(__file__).parent
QUEUE_FILE = HERE / "posts.txt"
POSTED_FILE = HERE / "posted.txt"
SEPARATOR = "---"
WINDOW = timedelta(hours=2)
MAX_CHARS = 500  # Threads の文字数上限


def current_slot(now: datetime, hours: list[int]) -> datetime | None:
    for hour in sorted(hours, reverse=True):
        for day_offset in (0, -1):
            slot = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
            if slot <= now < slot + WINDOW:
                return slot
    return None


def load_queue() -> list[str]:
    """posts.txt を「---」だけの行で区切って投稿のリストにする。// で始まる行はメモとして無視。"""
    if not QUEUE_FILE.exists():
        return []
    posts, lines = [], []
    for line in QUEUE_FILE.read_text().splitlines() + [SEPARATOR]:
        if line.strip() == SEPARATOR:
            text = "\n".join(lines).strip()
            if text:
                posts.append(text)
            lines = []
        elif not line.startswith("//"):
            lines.append(line)
    return posts


def save_queue(posts: list[str]) -> None:
    header = "".join(l + "\n" for l in QUEUE_FILE.read_text().splitlines() if l.startswith("//"))
    body = f"\n{SEPARATOR}\n".join(posts)
    QUEUE_FILE.write_text(header + body + ("\n" if body else ""))


def time_of_day(hour: int) -> str:
    if 5 <= hour < 11:
        return "朝"
    if 11 <= hour < 15:
        return "昼"
    if 15 <= hour < 18:
        return "夕方"
    return "夜"


def generate(now: datetime) -> str:
    persona = (HERE / "persona.md").read_text()
    recent = [p["text"] for p in threads_api.my_posts(limit=15) if p.get("text")]
    recent_list = "\n".join(f"- {t}" for t in recent) or "（まだありません）"
    prompt = (
        f"今は日本時間で{now:%Y年%m月%d日 %H:%M}（{time_of_day(now.hour)}）です。\n"
        "Threads に投稿する文章を1つ書いてください。\n\n"
        f"最近の投稿（内容や書き出しが重ならないようにしてください）:\n{recent_list}\n\n"
        "投稿本文だけを出力してください。前置き・説明・かぎかっこは不要です。300文字以内。"
    )
    for _ in range(2):
        text = gemini.generate(persona, prompt)
        if text and len(text) <= MAX_CHARS:
            return text
    raise RuntimeError(f"{MAX_CHARS}文字以内の投稿文を生成できませんでした")


def main() -> None:
    force = "--force" in sys.argv
    dry_run = os.environ.get("DRY_RUN") == "1" or "--dry-run" in sys.argv
    now = datetime.now(JST)
    hours = json.loads((HERE / "schedule.json").read_text())["hours_jst"]

    slot = current_slot(now, hours)
    if slot is None and not force:
        print(f"{now:%H:%M} は投稿時間帯ではありません（予定: {hours}時）")
        return

    if slot is not None and not force:
        recent = threads_api.my_posts(limit=1)
        if recent and threads_api.parse_time(recent[0]["timestamp"]) >= slot:
            print(f"{slot:%H時}の枠はすでに投稿済みです")
            return

    queue = load_queue()
    if queue:
        text, source = queue[0], f"posts.txt（残り{len(queue) - 1}件）"
        if len(text) > MAX_CHARS:
            sys.exit(f"先頭の投稿が{len(text)}文字あります。{MAX_CHARS}文字以内に直してください:\n{text}")
    else:
        text, source = generate(now), "AI生成"

    print(f"--- 投稿文 ({len(text)}文字) / {source} ---\n{text}\n---")
    if dry_run:
        print("DRY_RUN のため投稿はしていません")
        return
    print("投稿しました:", threads_api.publish_text(text))

    if queue:
        save_queue(queue[1:])
    with POSTED_FILE.open("a") as f:
        f.write(f"# {now:%Y-%m-%d %H:%M}（{source}）\n{text}\n{SEPARATOR}\n")


if __name__ == "__main__":
    main()
