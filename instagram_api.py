"""Instagram API（Instagram ログイン版）の薄いラッパー。"""
import os
import time

import requests

BASE = "https://graph.instagram.com"


def _token() -> str:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise SystemExit("環境変数 INSTAGRAM_ACCESS_TOKEN が設定されていません")
    return token


def _get(path: str, **params) -> dict:
    params["access_token"] = _token()
    r = requests.get(f"{BASE}/{path}", params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Instagram API エラー ({r.status_code}) GET {path}: {r.text[:500]}")
    return r.json()


def _post(path: str, **data) -> dict:
    data["access_token"] = _token()
    r = requests.post(f"{BASE}/{path}", data=data, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Instagram API エラー ({r.status_code}) POST {path}: {r.text[:500]}")
    return r.json()


def me() -> dict:
    """自分のアカウントの ID とユーザー名。"""
    return _get("me", fields="user_id,username")


def recent_captions(limit: int = 10) -> list[str]:
    data = _get("me/media", fields="caption,timestamp", limit=limit).get("data", [])
    return [m["caption"] for m in data if m.get("caption")]


def _wait_until_ready(container_id: str) -> None:
    for _ in range(30):
        status = _get(container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"投稿の準備に失敗しました: {status}")
        time.sleep(5)
    raise RuntimeError("投稿の準備が時間内に終わりませんでした")


def publish_carousel(image_urls: list[str], caption: str) -> str:
    """公開URLにある JPEG 画像（2〜10枚）をカルーセルとして投稿し、投稿IDを返す。"""
    user_id = me()["user_id"]
    children = []
    for url in image_urls:
        children.append(_post(f"{user_id}/media", image_url=url, is_carousel_item="true")["id"])
    for child in children:
        _wait_until_ready(child)
    container = _post(
        f"{user_id}/media", media_type="CAROUSEL", children=",".join(children), caption=caption
    )["id"]
    _wait_until_ready(container)
    return _post(f"{user_id}/media_publish", creation_id=container)["id"]


def refresh_token() -> str:
    """長期トークンを更新して新しいトークンを返す（有効期限が再び60日になる）。"""
    r = requests.get(
        f"{BASE}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": _token()},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"トークンの更新に失敗しました ({r.status_code}): {r.text[:300]}")
    return r.json()["access_token"]
