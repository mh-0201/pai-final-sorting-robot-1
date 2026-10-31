"""AIの変換が正しいかを、いろいろな言い回しで確かめるテスト。"""
import time
from ai_planner import plan

R, G, B = "red", "green", "blue"
CASES = [
    ("赤いブロックを右のトレイに入れて", [(R, "right")]),
    ("青いのを黄色い皿に置いてください", [(B, "left")]),
    ("緑を白いトレイへお願い", [(G, "right")]),
    ("赤と青を左に", [(R, "left"), (B, "left")]),
    ("まず緑を右、そのあと赤を左に移動して", [(G, "right"), (R, "left")]),
    ("全部右のトレイに片付けて", [(R, "right"), (G, "right"), (B, "right")]),
    ("紫のブロックを右に入れて", []),
    ("今日の天気は？", []),
    # 積み上げ
    ("赤いブロックを青いブロックの上に積んで", [(R, B)]),
    ("緑を赤の上にのせて", [(G, R)]),
    ("青の上に緑を重ねてください", [(G, B)]),
    ("赤を青に積んで、そのあと緑を赤の上に積んで", [(R, B), (G, R)]),
    ("赤を赤の上に積んで", []),
]

ok = 0
for text, expected in CASES:
    start = time.time()
    result = plan(text)
    got = [(a["cube"], a["place"]) for a in result["actions"]]
    passed = got == expected
    ok += passed
    print(f"{'○' if passed else '×'} {text} → {got}  「{result['reply']}」 ({time.time() - start:.1f}秒)")
    if not passed:
        print(f"    期待: {expected}")
print(f"正解 {ok}/{len(CASES)}")
