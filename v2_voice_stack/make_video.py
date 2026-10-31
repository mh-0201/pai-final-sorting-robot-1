"""提出用の動画を作る（v2: 声での会話と積み上げを追加）。

1. 録画: 3つの場面でAIに日本語の指示を出し、ロボットに仕分け・積み上げをさせる（raw_demo.mp4 / video_log.json）
   指示文とAIの返事は、Mac標準の読み上げ機能（say コマンド）で音声にする（voices/）
2. 編集: タイトル・しくみの説明・字幕・結果・音声を付けて final_video.mp4 にまとめる
3. YouTube用: 1つ上のフォルダにある OP・ED 動画を前後に付けて PAI最終課題_youtube.mp4 を作る

使い方:
  uv run python make_video.py                 # 録画から全部やる（事前に `ollama serve` を起動）
  uv run python make_video.py --compose-only  # 録画はそのままで、字幕や説明・音声の合成だけ作り直す
"""
import json
import os
import subprocess
import sys
import wave
import numpy as np
import imageio.v2 as imageio
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

FPS = 50
W, H = 1280, 720
RAW, LOG, OUT = "raw_demo.mp4", "video_log.json", "final_video.mp4"
SILENT = "final_video_silent.mp4"
VOICE_DIR = "voices"
OP, ED = "../PAI応用1_最終課題_OP.mp4", "../PAI応用1_最終課題_ED.mp4"
YOUTUBE = "PAI最終課題_youtube.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

HUMAN_VOICE = "Kyoko"  # 指示する人の声
ROBOT_VOICE = "Rocko"  # ロボットの声（機械らしい声）
SAMPLE_RATE = 24000
INTRO_SECONDS = 4 + 8  # タイトル画面としくみの説明画面の長さ（本編の音声をこの分ずらす）

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
    {
        "title": "場面3: 積み上げ",
        "layout": {"blue": (0.55, 0.0), "red": (0.65, -0.17), "green": (0.65, 0.17)},
        "instructions": [
            "赤いブロックを青の上に積んで",
            "その上に、緑ものせてください",
        ],
    },
]

CUBE_JA = {"red": "赤", "green": "緑", "blue": "青"}
TRAY_JA = {"left": "左（黄色）", "right": "右（白）"}


def place_ja(place):
    return TRAY_JA[place] if place in TRAY_JA else f"{CUBE_JA[place]}の上に積む"


# ---------------------------------------------------------------- 音声
def speak(text, voice, path):
    """text を読み上げた音声ファイルを作り、その長さ（秒）を返す。"""
    subprocess.run(["say", "-v", voice, "-o", path, f"--data-format=LEI16@{SAMPLE_RATE}", text], check=True)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)


# ---------------------------------------------------------------- 1. 録画
def record():
    from ai_planner import CUBE_NAMES, plan
    from robot import SortingWorld

    os.makedirs(VOICE_DIR, exist_ok=True)
    world = SortingWorld(video_path=RAW)
    events = []
    n_voice = 0

    def log(kind, **data):
        events.append({"time": round(world.sim_time, 2), "kind": kind, **data})

    for scene in SCENES:
        if scene["layout"]:
            world.reset_cubes(scene["layout"])
        log("scene", title=scene["title"])
        world.wait(100)
        remaining = list(CUBE_NAMES)
        history = []  # この場面で実行した動作（「その上」の解釈に使う）
        for text in scene["instructions"]:
            result = plan(text, remaining, history)
            print(f"[指示] {text}\n[AI] {result['reply']} {result['actions']}")

            # 人が指示を話す → ロボットが返事をする → 動く
            n_voice += 1
            human = f"{VOICE_DIR}/{n_voice:02d}_human.wav"
            robot = f"{VOICE_DIR}/{n_voice:02d}_robot.wav"
            human_sec = speak(text, HUMAN_VOICE, human)
            robot_sec = speak(result["reply"], ROBOT_VOICE, robot)
            log("instruction", text=text, voice=human)
            world.wait(int((human_sec + 0.5) * 100))
            log("reply", reply=result["reply"], actions=result["actions"], voice=robot)
            world.wait(int((robot_sec + 0.5) * 100))

            for a in result["actions"]:
                log("action", cube=a["cube"], place=a["place"])
                ok = world.pick_and_place(a["cube"], a["place"])
                log("result", cube=a["cube"], place=a["place"], ok=bool(ok))
                if ok:
                    history.append(a)
                    if a["cube"] in remaining:
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
        d.text((W / 2, y), text, font=font(size, thin=size < 30), fill=color, anchor="ma")
        y += size * 1.6
    return [np.array(img)] * int(seconds * FPS)


def overlay(frame, state):
    """シミュレーション映像の上に字幕を描く。"""
    img = Image.fromarray(frame).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 左上: 場面名と「等倍速」の表示
    d.rounded_rectangle((20, 20, 520, 64), 10, fill=(0, 0, 0, 150))
    d.text((36, 30), f"{state['scene']}（等倍速）", font=font(22), fill="white")

    # 下: 指示（人）と返事（ロボット）
    if state["instruction"]:
        d.rectangle((0, H - 120, W, H), fill=(0, 0, 0, 170))
        d.text((40, H - 108), f"人「{state['instruction']}」", font=font(30), fill=(255, 230, 120))
        if state["reply"]:
            d.text((40, H - 58), f"ロボット（AI）「{state['reply']}」", font=font(24, thin=True), fill="white")

    # 右上: AIが出した命令と、いま実行中の動作
    if state["reply"]:
        cmds = [f"{CUBE_JA[a['cube']]} → {place_ja(a['place'])}" for a in state["actions"]] or ["（実行しない）"]
        box_h = 60 + 34 * len(cmds)
        d.rounded_rectangle((W - 420, 20, W - 20, 20 + box_h), 10, fill=(0, 0, 0, 150))
        d.text((W - 404, 30), "AIが作った命令", font=font(20), fill=(150, 200, 255))
        for i, c in enumerate(cmds):
            active = state["current"] == i
            mark = "▶ " if active else ("✓ " if i < state["done"] else "　")
            d.text((W - 404, 62 + 34 * i), mark + c, font=font(24), fill=(120, 255, 160) if active else "white")

    return np.array(Image.alpha_composite(img, layer).convert("RGB"))


def compose():
    with open(LOG) as f:
        events = json.load(f)
    results = [e for e in events if e["kind"] == "result"]
    success = sum(e["ok"] for e in results)
    stacks = [e for e in results if e["place"] in CUBE_JA]

    writer = imageio.get_writer(SILENT, fps=FPS, codec="libx264", quality=8, macro_block_size=8)
    for frame in card(
        [
            ("ことばで指示する仕分けロボット", 56, (255, 255, 255)),
            ("話しかけると、ローカルの言語モデル（AI）が考えて、声で返事をして動く", 28, (200, 210, 230)),
            ("PAI最終課題 ／ Genesis シミュレーション × Ollama（qwen2.5:3b）", 24, (150, 170, 200)),
        ],
        4,
    ):
        writer.append_data(frame)
    for frame in card(
        [
            ("しくみ", 44, (255, 255, 255)),
            ("① 日本語で指示する　「赤いブロックを青の上に積んで」", 28, (255, 230, 120)),
            ("② AI（言語モデル）が命令に変換　{\"cube\": \"red\", \"place\": \"blue\"}", 28, (150, 200, 255)),
            ("③ ロボットが声で返事をする　「赤いブロックを青いブロックの上に積みます」", 28, (255, 200, 160)),
            ("④ 逆運動学（IK）で関節角度を計算し、つかむ → 運ぶ → 置く／積む", 28, (120, 255, 160)),
            ("無い色や関係のない指示には、動かずに理由を返す", 24, (200, 210, 230)),
            ("左右は「ロボットの正面に立つ人」から見た向き（画面と同じ）", 24, (200, 210, 230)),
        ],
        8,
    ):
        writer.append_data(frame)

    state = {"scene": "", "instruction": "", "reply": "", "actions": [], "current": None, "done": 0}
    queue = list(events)
    n_frames = 0
    for i, frame in enumerate(imageio.get_reader(RAW)):
        t = i / FPS
        while queue and queue[0]["time"] <= t:
            e = queue.pop(0)
            if e["kind"] == "scene":
                state.update(scene=e["title"], instruction="", reply="", actions=[], current=None, done=0)
            elif e["kind"] == "instruction":
                state.update(instruction=e["text"], reply="", actions=[], current=None, done=0)
            elif e["kind"] == "reply":
                state.update(reply=e["reply"], actions=e["actions"])
            elif e["kind"] == "action":
                state["current"] = state["done"]
            elif e["kind"] == "result":
                state["done"] += 1
                state["current"] = None
        writer.append_data(overlay(frame, state))
        n_frames = i + 1

    end_lines = [
        ("結果", 44, (255, 255, 255)),
        (f"仕分け・積み上げ {success} / {len(results)} 回 成功", 40, (120, 255, 160)),
        (f"うち積み上げ {sum(e['ok'] for e in stacks)} / {len(stacks)} 回（3段のタワー）", 28, (200, 210, 230)),
        ("無い色（紫）の指示には、動かずに声で「ありません」と返答", 28, (200, 210, 230)),
        ("今後: カメラ画像からブロックを見つける・音声認識で本当に話しかける", 24, (150, 170, 200)),
    ]
    for frame in card(end_lines, 5):
        writer.append_data(frame)
    writer.close()
    total = INTRO_SECONDS + n_frames / FPS + 5

    # 音声トラック: 各セリフを、動画の中で字幕が出るタイミングに置く
    track = np.zeros(int((total + 1) * SAMPLE_RATE), dtype=np.float32)
    for e in events:
        if "voice" in e:
            clip = read_wav(e["voice"])
            start = int((INTRO_SECONDS + e["time"]) * SAMPLE_RATE)
            track[start:start + len(clip)] += clip[: len(track) - start]
    track = np.clip(track, -32768, 32767).astype(np.int16)
    with wave.open("voices/track.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(track.tobytes())

    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", SILENT, "-i", "voices/track.wav",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", OUT],
        check=True,
    )
    os.remove(SILENT)
    print(f"{OUT} を保存しました（約 {total:.0f} 秒、成功 {success}/{len(results)}）")
    return total


# ---------------------------------------------------------------- 3. YouTube用
def duration(path):
    """動画の長さ（秒）を ffmpeg の出力から読み取る。"""
    probe = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True).stderr
    h, m, sec = probe.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def youtube(main_seconds):
    """OP + 本編 + ED をつないで 1920x1080 / 30fps にする。OP・ED の間は無音。"""
    if not (os.path.exists(OP) and os.path.exists(ED)):
        print("OP・ED の動画が見つからないため、YouTube用の動画は作りませんでした")
        return
    op_sec, ed_sec = duration(OP), duration(ED)
    op_ms = int(op_sec * 1000)
    total = op_sec + main_seconds + ed_sec
    fade_out = main_seconds - 0.4
    video = (
        "[0:v]scale=1920:1080,fps=30,setsar=1,format=yuv420p[op];"
        f"[1:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1,format=yuv420p,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out:.2f}:d=0.4[main];"
        "[2:v]scale=1920:1080,fps=30,setsar=1,format=yuv420p[ed];"
        "[op][main][ed]concat=n=3:v=1:a=0[v];"
        # 本編の音声を OP の長さだけ遅らせ、全体の長さまで無音で埋める（ED の間は無音）
        f"[1:a]adelay={op_ms}:all=1,apad=whole_dur={total:.2f}[a]"
    )
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", OP, "-i", OUT, "-i", ED, "-filter_complex", video,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", YOUTUBE],
        check=True,
    )
    print(f"{YOUTUBE} を保存しました")


if __name__ == "__main__":
    if "--compose-only" not in sys.argv:
        record()
    youtube(compose())
