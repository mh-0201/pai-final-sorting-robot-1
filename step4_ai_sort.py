"""ステップ4: 日本語の指示をAIで命令に変換し、ロボットに仕分けさせる。

使い方:
  uv run python step4_ai_sort.py              # 用意したデモ用の指示を順番に実行（動画を保存）
  uv run python step4_ai_sort.py --interactive  # 自分で指示を打ち込んで実行
"""
import json
import sys
from ai_planner import CUBE_NAMES, plan
from robot import SortingWorld

DEMO = [
    "青いブロックを黄色いトレイに入れて",
    "紫のブロックも片付けて",
    "残りは全部、白いトレイにお願い",
]

interactive = "--interactive" in sys.argv
world = SortingWorld(video_path=None if interactive else "step4_ai_sort.mp4")
remaining = list(CUBE_NAMES)
log = []  # 動画に字幕を付けるための記録（いつ・何を指示し・AIがどう答えたか）


def run(instruction):
    print(f"\n[指示] {instruction}")
    result = plan(instruction, remaining)
    print(f"[AI] {result['reply']}  命令: {result['actions']}")
    log.append({"time": round(world.sim_time, 2), "instruction": instruction, **result})
    for a in result["actions"]:
        if world.pick_and_place(a["cube"], a["tray"]) and a["cube"] in remaining:
            remaining.remove(a["cube"])
    world.wait(50)


if interactive:
    while (text := input("\n指示を入力（終了は空のままEnter）> ").strip()):
        run(text)
else:
    for text in DEMO:
        run(text)
    world.finish()
    with open("step4_log.json", "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\nstep4_ai_sort.mp4 と step4_log.json を保存しました（動画 {world.sim_time:.0f} 秒）")
