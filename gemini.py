"""Google Gemini API（無料枠）で文章を生成する。"""
import os
import time

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 無料枠で使える Flash 系の最新モデルを指す別名。混んでいるときは軽い Flash-Lite に切り替える
MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
ATTEMPTS_PER_MODEL = 2


def _request(key: str, model: str, body: dict) -> requests.Response:
    return requests.post(
        URL.format(model=model),
        headers={"x-goog-api-key": key},
        json=body,
        timeout=150,
    )


def generate(system: str, prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("環境変数 GEMINI_API_KEY が設定されていません")
    models = [os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else MODELS
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # 短い投稿文なので、じっくり考えさせずに速く返してもらう
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}},
    }

    last_error = ""
    for model in models:
        for attempt in range(ATTEMPTS_PER_MODEL):
            try:
                r = _request(key, model, body)
                if r.status_code == 400 and "thinking" in r.text.lower():
                    # 考える量の設定に対応していないモデルなら、設定を外して再送する
                    r = _request(key, model, {k: v for k, v in body.items() if k != "generationConfig"})
            except requests.RequestException as e:
                last_error = f"{model}: {e}"
                time.sleep(10 * (attempt + 1))
                continue

            if r.status_code == 429 or r.status_code >= 500:
                last_error = f"{model}: {r.status_code} {r.text[:300]}"
                time.sleep(10 * (attempt + 1))
                continue
            if not r.ok:
                raise RuntimeError(f"Gemini API エラー ({r.status_code}): {r.text[:500]}")

            candidates = r.json().get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if text:
                return text
            last_error = f"{model}: 空の応答 {r.text[:300]}"
        print(f"{model} で生成できなかったため、次のモデルを試します: {last_error}")

    raise SystemExit(f"Gemini で文章を生成できませんでした。次の実行で再試行します: {last_error}")
