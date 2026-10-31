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
# 置き場所: トレイ、またはブロックの色（そのブロックの上に積む）
PLACES = list(TRAY_NAMES) + list(CUBE_NAMES)

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
                    "place": {"type": "string", "enum": PLACES},
                },
                "required": ["cube", "place"],
            },
        },
        "reply": {"type": "string"},
    },
    "required": ["actions", "reply"],
}

SYSTEM_PROMPT = f"""あなたはブロックを仕分けたり積んだりするロボットの頭脳です。
ユーザーの日本語の指示を読み、ロボットが実行する動作の列（actions）と、ユーザーへの短い返事（reply）をJSONで出力します。

使えるブロック: {", ".join(f"{k}={v}" for k, v in CUBE_NAMES.items())}
使えるトレイ: {", ".join(f"{k}={v}" for k, v in TRAY_NAMES.items())}
置き場所(place): トレイ（left / right）か、ほかのブロックの色（red / green / blue。そのブロックの上に積む）

ルール:
- 1つの動作は {{"cube": 動かすブロック, "place": 置き場所}}。指示された順番に並べる。
- 「AをBの上に積んで」「AをBにのせて」は {{"cube": A, "place": B}}。cube と place に同じ色は使えない。
- 「全部」「すべて」は、まだ仕分けていないブロック全部を指す。
- 「その上」「いちばん上」「てっぺん」は、入力の「いちばん上のブロック」を place にする。
- 黄色いトレイ=left、白いトレイ=right。
- 存在しないブロックや意味の分からない指示の場合は actions を空にし、reply で理由を伝える。
- reply は日本語で1文。色は必ず「赤」「緑」「青」、トレイは「左」「右」と日本語で書き、red や left などの英語は使わない。
- reply はロボット自身が声に出して話す言葉なので、短く自然な話し言葉にする。

例:
指示「赤を右に入れて」→ {{"actions": [{{"cube": "red", "place": "right"}}], "reply": "赤いブロックを右のトレイに入れます。"}}
指示「青と緑を黄色いトレイへ」→ {{"actions": [{{"cube": "blue", "place": "left"}}, {{"cube": "green", "place": "left"}}], "reply": "青と緑のブロックを左のトレイに入れます。"}}
指示「赤を青の上に積んで」→ {{"actions": [{{"cube": "red", "place": "blue"}}], "reply": "赤いブロックを青いブロックの上に積みます。"}}
指示「その上に緑ものせて」（いちばん上のブロック: red）→ {{"actions": [{{"cube": "green", "place": "red"}}], "reply": "緑のブロックを赤いブロックの上にのせます。"}}
指示「紫のブロックを取って」→ {{"actions": [], "reply": "紫のブロックはありません。"}}
"""


def top_of_stack(history):
    """これまでの動作から、積み上げのいちばん上にあるブロックを求める（小さなモデルには推理させず、プログラムで計算する）。"""
    top = None
    for a in history:
        if a["place"] in CUBE_NAMES:
            top = a["cube"]  # ブロックの上に積んだら、それが新しいてっぺん
        elif a["cube"] == top:
            top = None  # てっぺんのブロックをトレイへ移したら、積み上げはなくなったとみなす
    return top


def plan(instruction, remaining=None, history=None):
    """指示文から命令を作る。

    remaining: まだ仕分けていないブロックのリスト（「全部」の解釈に使う）
    history: これまでに実行した動作のリスト（「その上」＝いちばん上のブロックを求めるのに使う）
    """
    remaining = remaining or list(CUBE_NAMES)
    names = ", ".join(f"{c}（{CUBE_NAMES[c]}）" for c in remaining)
    top = top_of_stack(history or [])
    top_text = f"{top}（{CUBE_NAMES[top]}）" if top else "なし"
    user = f"まだ仕分けていないブロック: {names}\nいちばん上のブロック: {top_text}\n指示「{instruction}」"
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
    valid = [
        a for a in result["actions"] if a.get("cube") in CUBE_NAMES and a.get("place") in PLACES and a["cube"] != a["place"]
    ]
    if len(valid) < len(result["actions"]):
        # 取り除いた命令があるときは、返事と実際の動作が食い違わないように返事も差し替える
        same = any(a.get("cube") == a.get("place") for a in result["actions"])
        result["reply"] = "同じブロックの上には積めません。" if same else "その指示の一部は実行できません。"
    result["actions"] = valid
    return result


if __name__ == "__main__":
    import sys

    print(json.dumps(plan(" ".join(sys.argv[1:]) or "赤いブロックを右のトレイに入れて"), ensure_ascii=False))
