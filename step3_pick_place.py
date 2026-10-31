"""ステップ3: 3つの色ブロックを、決められたトレイへ順番に仕分ける。"""
import time
from robot import SortingWorld

world = SortingWorld(video_path="step3_pick_place.mp4")
start = time.time()

plan = [("red", "right"), ("blue", "left"), ("green", "right")]
results = [world.pick_and_place(cube, tray) for cube, tray in plan]

world.finish()
print(f"成功 {sum(results)}/{len(results)} 件、{time.time() - start:.0f} 秒 / step3_pick_place.mp4 を保存しました")
