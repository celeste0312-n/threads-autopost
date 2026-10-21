"""Google Gemini API（無料枠）で文章を生成する。"""
import os

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 無料枠で使える Flash 系の最新モデルを指す別名。変えたいときは環境変数 GEMINI_MODEL で指定する
DEFAULT_MODEL = "gemini-flash-latest"


def generate(system: str, prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("環境変数 GEMINI_API_KEY が設定されていません")
    model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    r = requests.post(
        URL.format(model=model),
        headers={"x-goog-api-key": key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        },
        timeout=120,
    )
    if r.status_code == 429:
        raise SystemExit("Gemini の無料枠の上限に達しました。次の実行で再試行します")
    if not r.ok:
        raise RuntimeError(f"Gemini API エラー ({r.status_code}): {r.text[:500]}")
    candidates = r.json().get("candidates") or []
    if not candidates:
        raise RuntimeError(f"文章が生成されませんでした: {r.json()}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()
