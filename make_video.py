"""ステップ5: 提出用の動画を作る。

1. 録画: 2つの場面でAIに日本語の指示を出し、ロボットに仕分けさせる（raw_demo.mp4 / video_log.json）
2. 編集: タイトル・しくみの説明・字幕・結果を付けて final_video.mp4 にまとめる

使い方:
  uv run python make_video.py                 # 録画から全部やる（事前に `ollama serve` を起動）
  uv run python make_video.py --compose-only  # 録画はそのままで、字幕や説明だけ作り直す
"""
import json
import sys
import numpy as np
import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont

FPS = 50
W, H = 1280, 720
RAW, LOG, OUT = "raw_demo.mp4", "video_log.json", "final_video.mp4"

SCENES = [
    {
        "title": "場面1: 基本の仕分け",
        "layout": None,  # 最初の配置のまま
        "instructions": [
            "赤いブロックを黄色いトレイに入れて",
            "紫のブロックも片付けて",
            "残りは全部、右のトレイにお願い",
        ],
    },
    {
        "title": "場面2: 配置を変えて、順番つきの指示",
        "layout": {"red": (0.62, 0.12), "green": (0.52, -0.12), "blue": (0.66, -0.05)},
        "instructions": [
            "まず青を左に、そのあと緑も左に置いて",
            "赤は白いトレイへ",
        ],
    },
]

CUBE_JA = {"red": "赤", "green": "緑", "blue": "青"}
TRAY_JA = {"left": "左（黄色）", "right": "右（白）"}


# ---------------------------------------------------------------- 1. 録画
def record():
    from ai_planner import CUBE_NAMES, plan
    from robot import SortingWorld

    world = SortingWorld(video_path=RAW)
    events = []

    def log(kind, **data):
        events.append({"time": round(world.sim_time, 2), "kind": kind, **data})

    for scene in SCENES:
        if scene["layout"]:
            world.reset_cubes(scene["layout"])
        log("scene", title=scene["title"])
        world.wait(100)
        remaining = list(CUBE_NAMES)
        for text in scene["instructions"]:
            result = plan(text, remaining)
            print(f"[指示] {text}\n[AI] {result['reply']} {result['actions']}")
            log("instruction", text=text, reply=result["reply"], actions=result["actions"])
            world.wait(120)  # 字幕を読む時間
            for a in result["actions"]:
                log("action", cube=a["cube"], tray=a["tray"])
                ok = world.pick_and_place(a["cube"], a["tray"])
                log("result", cube=a["cube"], tray=a["tray"], ok=bool(ok))
                if ok and a["cube"] in remaining:
                    remaining.remove(a["cube"])
            world.wait(100)
    log("end")
    world.finish()
    with open(LOG, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 2. 編集
FONT_PATH = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_THIN = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"


def font(size, thin=False):
    return ImageFont.truetype(FONT_THIN if thin else FONT_PATH, size)


def card(lines, seconds):
    """黒背景に文字を並べた説明画面。lines = [(文字, 大きさ, 色), ...]"""
    img = Image.new("RGB", (W, H), (18, 24, 38))
    d = ImageDraw.Draw(img)
    total = sum(size * 1.6 for _, size, _ in lines)
    y = (H - total) / 2
    for text, size, color in lines:
        f = font(size, thin=size < 30)
        d.text((W / 2, y), text, font=f, fill=color, anchor="ma")
        y += size * 1.6
    frame = np.array(img)
    return [frame] * int(seconds * FPS)


def overlay(frame, state):
    """シミュレーション映像の上に字幕を描く。"""
    img = Image.fromarray(frame).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 左上: 場面名と「等倍速」の表示
    d.rounded_rectangle((20, 20, 520, 64), 10, fill=(0, 0, 0, 150))
    d.text((36, 30), f"{state['scene']}（等倍速）", font=font(22), fill="white")

    # 下: 指示とAIの返事
    if state["instruction"]:
        d.rectangle((0, H - 120, W, H), fill=(0, 0, 0, 170))
        d.text((40, H - 108), f"指示「{state['instruction']}」", font=font(30), fill=(255, 230, 120))
        d.text((40, H - 58), f"AI：{state['reply']}", font=font(24, thin=True), fill="white")

    # 右上: AIが出した命令（JSON）と、いま実行中の動作
    if state["instruction"]:
        cmds = [f"{CUBE_JA[a['cube']]} → {TRAY_JA[a['tray']]}" for a in state["actions"]] or ["（実行しない）"]
        box_h = 60 + 34 * len(cmds)
        d.rounded_rectangle((W - 400, 20, W - 20, 20 + box_h), 10, fill=(0, 0, 0, 150))
        d.text((W - 384, 30), "AIが作った命令", font=font(20), fill=(150, 200, 255))
        for i, c in enumerate(cmds):
            active = state["current"] == i
            mark = "▶ " if active else ("✓ " if i < state["done"] else "　")
            d.text((W - 384, 62 + 34 * i), mark + c, font=font(24), fill=(120, 255, 160) if active else "white")

    return np.array(Image.alpha_composite(img, layer).convert("RGB"))


def compose():
    with open(LOG) as f:
        events = json.load(f)
    results = [e for e in events if e["kind"] == "result"]
    success = sum(e["ok"] for e in results)

    writer = imageio.get_writer(OUT, fps=FPS, codec="libx264", quality=8, macro_block_size=8)
    for frame in card(
        [
            ("ことばで指示する仕分けロボット", 56, (255, 255, 255)),
            ("日本語の指示を、ローカルの言語モデル（AI）がロボットの命令に変換", 28, (200, 210, 230)),
            ("PAI最終課題 ／ Genesis シミュレーション × Ollama（qwen2.5:3b）", 24, (150, 170, 200)),
        ],
        4,
    ):
        writer.append_data(frame)
    for frame in card(
        [
            ("しくみ", 44, (255, 255, 255)),
            ("① 日本語で指示する　「赤いブロックを黄色いトレイに入れて」", 28, (255, 230, 120)),
            ("② AI（言語モデル）が命令に変換　{\"cube\": \"red\", \"tray\": \"left\"}", 28, (150, 200, 255)),
            ("③ 逆運動学（IK）で関節角度を計算し、つかむ → 運ぶ → 置く", 28, (120, 255, 160)),
            ("無い色や関係のない指示には、動かずに理由を返す", 24, (200, 210, 230)),
            ("左右は「ロボットの正面に立つ人」から見た向き（画面と同じ）", 24, (200, 210, 230)),
        ],
        8,
    ):
        writer.append_data(frame)

    state = {"scene": "", "instruction": "", "reply": "", "actions": [], "current": None, "done": 0}
    queue = list(events)
    for i, frame in enumerate(imageio.get_reader(RAW)):
        t = i / FPS
        while queue and queue[0]["time"] <= t:
            e = queue.pop(0)
            if e["kind"] == "scene":
                state.update(scene=e["title"], instruction="", reply="", actions=[], current=None, done=0)
            elif e["kind"] == "instruction":
                state.update(instruction=e["text"], reply=e["reply"], actions=e["actions"], current=None, done=0)
            elif e["kind"] == "action":
                state["current"] = state["done"]
            elif e["kind"] == "result":
                state["done"] += 1
                state["current"] = None
        writer.append_data(overlay(frame, state))

    for frame in card(
        [
            ("結果", 44, (255, 255, 255)),
            (f"仕分け {success} / {len(results)} 回 成功", 40, (120, 255, 160)),
            ("無い色（紫）の指示には、動かずに「ありません」と返答", 28, (200, 210, 230)),
            ("今後: カメラ画像からブロックを見つける・積み上げなど指示の種類を増やす", 24, (150, 170, 200)),
        ],
        5,
    ):
        writer.append_data(frame)
    writer.close()
    total = 4 + 8 + (i + 1) / FPS + 5
    print(f"{OUT} を保存しました（約 {total:.0f} 秒、成功 {success}/{len(results)}）")


if __name__ == "__main__":
    if "--compose-only" not in sys.argv:
        record()
    compose()
