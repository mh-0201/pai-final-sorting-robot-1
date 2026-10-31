"""AIの部分: 日本語の指示文を、言語モデルでロボットの命令（JSON）に変換する。

Mac上で動くローカルの言語モデル（Ollama + qwen2.5:3b）を使う。推論のみで、学習はしない。
事前に別のターミナルで `ollama serve` を起動しておくこと。
"""
import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"

CUBE_NAMES = {"red": "赤", "green": "緑", "blue": "青"}
TRAY_NAMES = {"left": "左（黄色）", "right": "右（白）"}

# 言語モデルに守らせる出力の形（Ollama の structured outputs 機能でこの形しか出せなくなる）
SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cube": {"type": "string", "enum": list(CUBE_NAMES)},
                    "tray": {"type": "string", "enum": list(TRAY_NAMES)},
                },
                "required": ["cube", "tray"],
            },
        },
        "reply": {"type": "string"},
    },
    "required": ["actions", "reply"],
}

SYSTEM_PROMPT = f"""あなたはブロック仕分けロボットの指令係です。
ユーザーの日本語の指示を読み、ロボットが実行する動作の列（actions）と、ユーザーへの短い返事（reply）をJSONで出力します。

使えるブロック: {", ".join(f"{k}={v}" for k, v in CUBE_NAMES.items())}
使えるトレイ: {", ".join(f"{k}={v}" for k, v in TRAY_NAMES.items())}

ルール:
- 1つの動作は {{"cube": ブロック, "tray": トレイ}}。指示された順番に並べる。
- 「全部」「すべて」は、まだ仕分けていないブロック全部を指す。
- 黄色いトレイ=left、白いトレイ=right。
- 存在しないブロックや意味の分からない指示の場合は actions を空にし、reply で理由を伝える。
- reply は日本語で1文。色は必ず「赤」「緑」「青」、トレイは「左」「右」と日本語で書き、red や left などの英語は使わない。

例:
指示「赤を右に入れて」→ {{"actions": [{{"cube": "red", "tray": "right"}}], "reply": "赤いブロックを右のトレイに入れます。"}}
指示「青と緑を黄色いトレイへ」→ {{"actions": [{{"cube": "blue", "tray": "left"}}, {{"cube": "green", "tray": "left"}}], "reply": "青と緑のブロックを左のトレイに入れます。"}}
指示「紫のブロックを取って」→ {{"actions": [], "reply": "紫のブロックはありません。"}}
"""


def plan(instruction, remaining=None):
    """指示文から命令を作る。remaining はまだ仕分けていないブロックのリスト（「全部」の解釈に使う）。"""
    remaining = remaining or list(CUBE_NAMES)
    names = ", ".join(f"{c}（{CUBE_NAMES[c]}）" for c in remaining)
    user = f"まだ仕分けていないブロック: {names}\n指示「{instruction}」"
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0},  # 毎回同じ答えになるようにする
    }
    req = urllib.request.Request(OLLAMA_URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as res:
        result = json.loads(json.loads(res.read())["message"]["content"])

    # 念のため、ロボットが実行できない命令は取り除く
    result["actions"] = [
        a for a in result["actions"] if a.get("cube") in CUBE_NAMES and a.get("tray") in TRAY_NAMES
    ]
    return result


if __name__ == "__main__":
    import sys

    print(json.dumps(plan(" ".join(sys.argv[1:]) or "赤いブロックを右のトレイに入れて"), ensure_ascii=False))
