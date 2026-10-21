"""過去の投稿の閲覧数から、よく見られる時間帯（日本時間）を選んで schedule.json に保存する。"""
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import threads_api

JST = timezone(timedelta(hours=9))
SCHEDULE_FILE = Path(__file__).with_name("schedule.json")

POSTS_PER_DAY = 3          # 1日の投稿回数
MIN_GAP_HOURS = 3          # 投稿どうしの最低間隔
CANDIDATE_HOURS = range(6, 24)  # 深夜帯（0〜5時）は使わない
DEFAULT_HOURS = [7, 12, 21]     # データが少ないときの定番時間帯
MIN_POSTS = 10             # これ未満なら定番時間帯を使う
MIN_SAMPLES_PER_HOUR = 2   # 1時間帯あたり最低この件数がないと評価しない


def pick_hours(avg_by_hour: dict[int, float]) -> list[int]:
    chosen: list[int] = []
    for hour in sorted(avg_by_hour, key=avg_by_hour.get, reverse=True):
        if all(min(abs(hour - h), 24 - abs(hour - h)) >= MIN_GAP_HOURS for h in chosen):
            chosen.append(hour)
        if len(chosen) == POSTS_PER_DAY:
            break
    # 足りない分は定番時間帯で補う
    for hour in DEFAULT_HOURS:
        if len(chosen) == POSTS_PER_DAY:
            break
        if all(abs(hour - h) >= MIN_GAP_HOURS for h in chosen):
            chosen.append(hour)
    return sorted(chosen)


def main() -> None:
    now = datetime.now(timezone.utc)
    views_by_hour: dict[int, list[int]] = defaultdict(list)
    for post in threads_api.my_posts(limit=100):
        posted_at = threads_api.parse_time(post["timestamp"])
        if now - posted_at < timedelta(hours=24):
            continue  # 閲覧数がまだ伸びている最中の投稿は除外
        views = threads_api.post_views(post["id"])
        if views is not None:
            views_by_hour[posted_at.astimezone(JST).hour].append(views)

    total = sum(len(v) for v in views_by_hour.values())
    avg_by_hour = {
        h: sum(v) / len(v)
        for h, v in views_by_hour.items()
        if h in CANDIDATE_HOURS and len(v) >= MIN_SAMPLES_PER_HOUR
    }

    if total < MIN_POSTS or not avg_by_hour:
        hours = DEFAULT_HOURS
        reason = f"分析できる投稿が{total}件と少ないため、定番の時間帯を使用"
    else:
        hours = pick_hours(avg_by_hour)
        reason = f"過去{total}件の平均閲覧数から選択"
        # 同じ時間帯ばかりにならないよう、試したことの少ない時間帯を1枠だけ試す
        untested = [h for h in CANDIDATE_HOURS
                    if len(views_by_hour.get(h, [])) < MIN_SAMPLES_PER_HOUR]
        if untested and len(hours) == POSTS_PER_DAY:
            weakest = min(hours, key=lambda h: avg_by_hour.get(h, 0))
            rest = [h for h in hours if h != weakest]
            untested = [h for h in untested if all(abs(h - c) >= MIN_GAP_HOURS for c in rest)]
            if untested:
                trial = random.choice(untested)
                hours = sorted(rest + [trial])
                reason += f"（{trial}時はお試し枠）"

    schedule = {
        "hours_jst": hours,
        "reason": reason,
        "avg_views_by_hour": {str(h): round(avg_by_hour[h]) for h in sorted(avg_by_hour)},
        "updated_at": now.astimezone(JST).isoformat(timespec="minutes"),
    }
    SCHEDULE_FILE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(schedule, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
