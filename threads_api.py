"""Threads API の薄いラッパー。"""
import os
import re
import time
from datetime import datetime

import requests

BASE = "https://graph.threads.net/v1.0"


def _token() -> str:
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        raise SystemExit("環境変数 THREADS_ACCESS_TOKEN が設定されていません")
    return token


def _get(path: str, **params) -> dict:
    params["access_token"] = _token()
    r = requests.get(f"{BASE}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, **data) -> dict:
    data["access_token"] = _token()
    r = requests.post(f"{BASE}/{path}", data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_time(ts: str) -> datetime:
    # 例: "2026-10-21T12:34:56+0000"
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def my_posts(limit: int = 100) -> list[dict]:
    """自分の投稿を新しい順に最大 limit 件取得する。"""
    posts: list[dict] = []
    page = _get("me/threads", fields="id,text,timestamp,media_type", limit=min(limit, 100))
    while True:
        posts.extend(page.get("data", []))
        next_url = page.get("paging", {}).get("next")
        if len(posts) >= limit or not next_url:
            break
        r = requests.get(next_url, timeout=30)
        r.raise_for_status()
        page = r.json()
    return posts[:limit]


def post_views(media_id: str) -> int | None:
    """投稿の閲覧数。取得できない投稿（リポストなど）は None。"""
    try:
        data = _get(f"{media_id}/insights", metric="views")["data"]
    except requests.HTTPError:
        return None
    for metric in data:
        if metric.get("name") == "views":
            if "total_value" in metric:
                return metric["total_value"]["value"]
            return metric["values"][0]["value"]
    return None


def split_topic_tag(text: str) -> tuple[str, str | None]:
    """本文の最後にある「#タグ」を取り出し、(タグを除いた本文, タグ) を返す。"""
    m = re.search(r"\s*[#＃]([^\s#＃]+)\s*$", text)
    if not m:
        return text, None
    tag = re.sub(r"[.&]", "", m.group(1))[:50]  # Threads のタグに「.」「&」は使えない
    if not tag:
        return text, None
    return text[: m.start()].rstrip(), tag


def publish_text(text: str) -> str:
    """テキスト投稿を作成して公開し、投稿IDを返す。最後の #タグ はトピックとして付ける。"""
    body, tag = split_topic_tag(text)
    try:
        if tag:
            container_id = _post("me/threads", media_type="TEXT", text=body, topic_tag=tag)["id"]
        else:
            container_id = _post("me/threads", media_type="TEXT", text=text)["id"]
    except requests.HTTPError as e:
        if not tag:
            raise
        # トピックの指定でエラーになったら、タグを本文に残したまま投稿する
        print(f"トピック「{tag}」を付けられなかったため、本文に残して投稿します: {e.response.text[:300]}")
        container_id = _post("me/threads", media_type="TEXT", text=text)["id"]
    for _ in range(10):
        status = _get(container_id, fields="status").get("status")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"投稿の準備に失敗しました: {status}")
        time.sleep(3)
    return _post("me/threads_publish", creation_id=container_id)["id"]


def refresh_token() -> str:
    """長期トークンを更新して新しいトークンを返す（有効期限が再び60日になる）。"""
    r = requests.get(
        "https://graph.threads.net/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": _token()},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]
