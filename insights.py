"""Generate per-category AI commentary (Gemini) from macro.json / macro.local.json.

Public mode (default): reads macro.json, writes insights.json. Restricted indicators are dropped from the
input entirely, so no restricted value ever reaches the prompt or the output.
Local mode (--local): reads macro.local.json, writes the gitignored insights.local.json.
The API key comes from GEMINI_API_KEY (GitHub secret or .env); without it every card shows "unavailable".
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fetch_macro import load_dotenv

PROMPT_VERSION = "1"
DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DISCLAIMER = "AI生成・投資助言ではありません。数値は同ダッシュボードの取得値のみに基づきます。"
MIN_HISTORY = 30
STATUS_JA = {
    "ok": "取得済み",
    "stale": "古い(最終観測が古く現在値ではない)",
    "pending": "データ無し(未接続)",
    "link_only": "データ無し(リンクのみ)",
    "unavailable": "データ無し(取得失敗)",
    "restricted": "対象外",
}
# Public output is rejected if the model names restricted series that were never provided.
RESTRICTED_TERMS = re.compile(
    r"OAS|SPY|RSP|VIX|プット\s*/\s*コール|put\s*/\s*call|200日線乖離|"
    r"\bA/D\b|A／D|騰落\s*\(A/D\)|advance[\s-]*decline|breadth|上昇の広がり|"
    r"Wilshire 5000|NYSE Composite|Nasdaq Composite|Dow Jones Industrial Average",
    re.IGNORECASE,
)

PERSONA = """あなたは機関投資家出身のマクロ・ストラテジストです。冷静で慎重、過度に断定しません。
# ルール
- 入力JSONに含まれる数値・日付だけを使い、入力にない数値・指標・出来事は一切書かない(推測で補わない)。
- status が「データ無し」「古い」の指標は、その旨を明示し、現状の判断材料にしない。
- 買い・売りなどの投資助言や断定、総合スコア化はしない。「〜と読める」「〜の可能性」といった表現にする。
- 歴史的位置は percentile がある指標のみ言及する。履歴が短い指標では位置を論じない。
- 最後に必ず「不確実性」と「この見方が崩れる条件(反証条件)」をそれぞれ1文で述べる。
- 日本語、4〜6行程度の簡潔な短い段落。見出しや箇条書きの装飾は不要。"""

SUMMARY_PERSONA = """あなたは機関投資家出身のマクロ・ストラテジストです。入力はカテゴリ別の分析文です。
入力にある内容だけを使って、全体俯瞰を3〜4行の日本語で述べてください。総合スコア・断定・投資助言は禁止。
データ無し/古い指標が多い場合は、その限界を明記し、最後に不確実性を1文で述べてください。"""


def _status_label(status):
    return STATUS_JA.get(status, "データ無し")


def indicator_input(indicator):
    status = indicator.get("status", "unavailable")
    item = {"name": indicator.get("name"), "status": _status_label(status),
            "frequency": indicator.get("frequency")}
    latest = indicator.get("latest")
    if status in ("ok", "stale") and latest:
        item["latest_value"] = latest.get("value")
        item["unit"] = indicator.get("unit", "")
        item["last_observation"] = latest.get("date")
        stats = indicator.get("stats") or {}
        if (stats.get("count") or 0) >= MIN_HISTORY:
            item["percentile_in_history"] = stats.get("percentile")
            item["history_start"] = stats.get("start")
            item["history_median"] = stats.get("median")
        else:
            item["history_note"] = f"観測{stats.get('count', 0)}日と短く歴史的位置は評価不可"
        if indicator.get("formula"):
            item["formula"] = indicator["formula"]
    elif indicator.get("reason"):
        item["reason"] = indicator["reason"]
    return item


def build_category_inputs(data, allow_restricted):
    """Return {group_id: {"name", "indicators": [...], "usable": int}}; restricted data is excluded in public mode."""
    if not allow_restricted and data.get("local_only"):
        raise ValueError("local data must not be used for public insights")
    categories = {}
    for group in data.get("groups", []):
        items = []
        usable = 0
        for ind in data.get("indicators", []):
            if ind.get("group") != group["id"]:
                continue
            if ind.get("status") == "restricted" or (not allow_restricted and ind.get("restricted")):
                continue
            item = indicator_input(ind)
            items.append(item)
            usable += 1 if ind.get("status") in ("ok", "stale") and ind.get("latest") else 0
        if items:
            categories[group["id"]] = {"name": group["name"], "indicators": items, "usable": usable}
    return categories


def input_hash(payload):
    raw = json.dumps([PROMPT_VERSION, payload], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def call_gemini(system_prompt, user_text, api_key, models, post=None):
    """One call per request; tries the next model only on failure. Returns (text, model). Never logs the key."""
    post = post or _post
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    last_error = "no model"
    for model in models:
        try:
            result = post(ENDPOINT.format(model=model), body, api_key)
            parts = result["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
            if text:
                return text, model
            last_error = "empty response"
        except Exception as exc:
            last_error = type(exc).__name__
    raise RuntimeError(last_error)


def _post(url, body, api_key, timeout=60):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _unavailable(reason, digest=None):
    return {"status": "unavailable", "reason": reason, "input_hash": digest}


def _safe_text(text, allow_restricted):
    return allow_restricted or not RESTRICTED_TERMS.search(text)


def generate_insights(data, previous=None, api_key=None, allow_restricted=False, models=None, post=None, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = previous or {}
    models = models or DEFAULT_MODELS
    categories = build_category_inputs(data, allow_restricted)
    out = {"generated_at": stamp, "disclaimer": DISCLAIMER, "model": None,
           "local_only": allow_restricted, "categories": {}, "summary": None}
    used_models = set()

    def generate(system_prompt, text):
        result, model = call_gemini(system_prompt, text, api_key, models, post)
        if not _safe_text(result, allow_restricted):
            raise ValueError("restricted terms in output")
        used_models.add(model)
        return result, model

    for group_id, cat in categories.items():
        digest = input_hash(cat["indicators"])
        old = (previous.get("categories") or {}).get(group_id) or {}
        if cat["usable"] == 0:
            out["categories"][group_id] = _unavailable("分析できる取得済みデータがありません。", digest)
        elif old.get("status") == "ok" and old.get("input_hash") == digest and _safe_text(old.get("text", ""), allow_restricted):
            out["categories"][group_id] = old
        elif not api_key:
            out["categories"][group_id] = _unavailable("GEMINI_API_KEY が未設定のため未生成です。", digest)
        else:
            try:
                prompt = f"カテゴリ: {cat['name']}\n指標データ:\n" + json.dumps(cat["indicators"], ensure_ascii=False)
                text, model = generate(PERSONA, prompt)
                out["categories"][group_id] = {"status": "ok", "text": text, "model": model,
                                               "generated_at": stamp, "input_hash": digest}
            except Exception as exc:
                out["categories"][group_id] = _unavailable(f"生成に失敗しました ({type(exc).__name__})。", digest)

    ready = {gid: c for gid, c in out["categories"].items() if c["status"] == "ok"}
    if ready:
        digest = input_hash({gid: c["text"] for gid, c in ready.items()})
        old = previous.get("summary") or {}
        if old.get("status") == "ok" and old.get("input_hash") == digest and _safe_text(old.get("text", ""), allow_restricted):
            out["summary"] = old
        elif api_key:
            try:
                names = {gid: categories[gid]["name"] for gid in ready}
                payload = {names[gid]: c["text"] for gid, c in ready.items()}
                text, model = generate(SUMMARY_PERSONA, json.dumps(payload, ensure_ascii=False))
                out["summary"] = {"status": "ok", "text": text, "model": model,
                                  "generated_at": stamp, "input_hash": digest}
            except Exception as exc:
                out["summary"] = _unavailable(f"生成に失敗しました ({type(exc).__name__})。", digest)
    used = {c.get("model") for c in list(out["categories"].values()) + [out["summary"] or {}] if c.get("model")}
    out["model"] = ", ".join(sorted(used)) or None
    return out


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate AI category commentary.")
    parser.add_argument("--local", action="store_true",
                        help="use macro.local.json (incl. restricted data) and write gitignored insights.local.json")
    args = parser.parse_args(argv)
    base = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base, ".env"))
    source = os.path.join(base, "macro.local.json" if args.local else "macro.json")
    target = os.path.join(base, "insights.local.json" if args.local else "insights.json")
    data = _load_json(source)
    if not data:
        print(f"{os.path.basename(source)} not found; run fetch_macro.py first")
        return 1
    models = [m.strip() for m in os.environ.get("GEMINI_MODEL", "").split(",") if m.strip()] or None
    result = generate_insights(data, previous=_load_json(target), api_key=os.environ.get("GEMINI_API_KEY") or None,
                               allow_restricted=args.local, models=models)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)
    counts = {}
    for cat in result["categories"].values():
        counts[cat["status"]] = counts.get(cat["status"], 0) + 1
    print(f"{os.path.basename(target)} written:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
