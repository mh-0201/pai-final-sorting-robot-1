"""ステップ2: 逆運動学（IK）で、アームの手先を狙った位置へ動かす。

IK = 「手先をこの位置・向きにしたい」から「各関節の角度」を逆算する計算。
いくつかの目標位置を順番に回り、実際に届いた位置との誤差を表示して動画に保存する。
"""
import numpy as np
import genesis as gs

gs.init(backend=gs.gpu, logging_level="warning")

scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=0.01))
scene.add_entity(gs.morphs.Plane())
scene.add_entity(gs.morphs.Box(size=(0.04, 0.04, 0.04), pos=(0.65, 0.0, 0.02)))
franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
cam = scene.add_camera(res=(640, 480), pos=(1.8, -1.4, 1.0), lookat=(0.5, 0.0, 0.2), fov=40)
scene.build()

# 関節を目標角度に追従させる強さ（PD制御のゲイン）。7関節 + 指2本
franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))

hand = franka.get_link("hand")
DOWN = np.array([0.0, 1.0, 0.0, 0.0])  # 手先を真下に向ける姿勢（クォータニオン w, x, y, z）


def move_to(pos, steps=150, settle=50):
    """手先を pos へ動かす。今の関節角度からIKの解まで、少しずつ補間して滑らかに動かす。"""
    start = franka.get_dofs_position()
    goal = franka.inverse_kinematics(link=hand, pos=np.array(pos), quat=DOWN)
    goal[-2:] = 0.04  # 指は開いたまま
    for i in range(steps + settle):
        t = min(i / steps, 1.0)
        t = t * t * (3 - 2 * t)  # 動き始めと終わりをゆっくりにする
        franka.control_dofs_position(start + (goal - start) * t)
        scene.step()
        cam.render()
    error = np.linalg.norm(hand.get_pos().cpu().numpy() - np.array(pos))
    print(f"目標 {pos} → 誤差 {error * 1000:.1f} mm")
    return error


targets = [
    (0.65, 0.0, 0.25),   # 立方体の真上
    (0.65, 0.0, 0.13),   # 立方体をつかめる高さ（手首から指先まで約10cmあるため）
    (0.65, 0.0, 0.25),   # 持ち上げる高さに戻る
    (0.45, 0.30, 0.25),  # 左手前へ
    (0.45, -0.30, 0.25), # 右手前へ
]

cam.start_recording(save_to_filename="step2_ik.mp4", fps=50)
errors = [move_to(p) for p in targets]
cam.stop_recording()
print(f"最大誤差 {max(errors) * 1000:.1f} mm / step2_ik.mp4 を保存しました")
