"""AI gateway 呼叫：OpenAI 相容 /chat/completions，strict JSON schema，可附圖。

模型只寫語意別名（sky-fast／sky-quality），實際對應哪個上游模型由 ai-gateway 決定；
回應的 model 欄位是實際作答的模型，呼叫端連同別名一起記錄。
"""

import base64
import json
import random
import time

import requests

FAST = "sky-fast"  # 大量抽取／分類
QUALITY = "sky-quality"  # 給人看的判讀與審核
RETRY_STATUS = (429, 500, 502, 503, 504)


def extraction_model(env):
    return env.get("CHUMEI_LLM_MODEL") or FAST


def review_model(env):
    return env.get("CHUMEI_REVIEW_MODEL") or QUALITY


def file_data_url(path, ctype="image/jpeg"):
    with open(path, "rb") as f:
        return f"data:{ctype};base64,{base64.b64encode(f.read()).decode()}"


def load_schema(path):
    with open(path) as f:
        return json.load(f)


def chat_json(env, model, system, text, *, images=(), schema=None, schema_name="result",
              timeout=180, attempts=5):
    """送一輪對話，回傳 (JSON 字串, 實際作答的模型)。

    images 是 data URL 清單。schema 給了就用 strict json_schema，否則 json_object。
    429／5xx／連線錯誤指數退避重試；400 直接拋出。
    """
    if not env.get("CHUMEI_LLM_API_KEY"):
        raise RuntimeError("missing CHUMEI_LLM_API_KEY")
    content = [{"type": "text", "text": text}]
    content += [{"type": "image_url", "image_url": {"url": url}} for url in images]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": (
            {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
            if schema else {"type": "json_object"}
        ),
    }
    base = env.get("CHUMEI_LLM_BASE_URL") or "http://127.0.0.1:8317/v1"
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            resp = requests.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {env['CHUMEI_LLM_API_KEY']}"},
                json=payload, timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout):
            if last:
                raise
            resp = None
        if resp is not None and resp.status_code not in RETRY_STATUS:
            if resp.status_code == 400:
                raise RuntimeError(f"400: {resp.text[:200]}")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], data.get("model") or model
        if last:
            break
        time.sleep(min(120, 8 * (2 ** attempt)) + random.uniform(0, 4))
    raise RuntimeError(f"gateway unavailable after {attempts} attempts"
                       + (f" (HTTP {resp.status_code})" if resp is not None else ""))
