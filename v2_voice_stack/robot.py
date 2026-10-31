"""仕分けロボットの部品: シーンの作成と、ピック＆プレース（つかむ→運ぶ→置く）の動作。

ステップ3以降のスクリプトはこのファイルを読み込んで使う。
"""
import numpy as np
import genesis as gs

# 色ブロックの初期位置 (x, y) と色 (R, G, B)
CUBES = {
    "red": ((0.55, -0.15), (0.9, 0.15, 0.15)),
    "green": ((0.65, 0.0), (0.2, 0.8, 0.3)),
    "blue": ((0.55, 0.15), (0.2, 0.4, 0.95)),
}
# ブロックを置くトレイの位置 (x, y) と色。
# 左右は「ロボットの正面に立って指示する人」から見た向き（カメラの画面とも一致する）
TRAYS = {
    "left": ((0.35, -0.40), (0.95, 0.85, 0.3)),
    "right": ((0.35, 0.40), (0.9, 0.9, 0.9)),
}
CUBE_SIZE = 0.04
TRAY_SIZE = 0.14
TRAY_HEIGHT = 0.01
SLOTS = [0.03, -0.03, 0.0]  # トレイ中心からの x 方向のずらし幅（置く順に使う）

DOWN = np.array([0.0, 1.0, 0.0, 0.0])  # 手先を真下に向ける姿勢（クォータニオン w, x, y, z）
GRASP_Z = 0.13  # ブロックをつかむときの手首の高さ（手首から指先まで約10cm）
HAND_OFFSET = GRASP_Z - CUBE_SIZE / 2  # ブロックの中心から、つかむときの手首までの高さ
LIFT_Z = 0.28   # 運ぶときの手首の高さ
ARM = np.arange(7)  # 腕の関節番号
FINGERS = np.array([7, 8])  # 指の関節番号
GRIP_FORCE = 3.0  # つかむ力 [N]（1N では運ぶ途中に落とすことがあり、8N では積む位置がずれた）
HOME = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04])  # 待機姿勢の関節角度


class SortingWorld:
    def __init__(self, video_path=None):
        gs.init(backend=gs.gpu, logging_level="warning")
        self.scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=0.01))
        self.scene.add_entity(gs.morphs.Plane())

        self.trays = {}
        for name, ((x, y), color) in TRAYS.items():
            self.scene.add_entity(
                gs.morphs.Box(size=(TRAY_SIZE, TRAY_SIZE, TRAY_HEIGHT), pos=(x, y, TRAY_HEIGHT / 2), fixed=True),
                surface=gs.surfaces.Default(color=color),
            )
            self.trays[name] = np.array([x, y])
        self.tray_count = {name: 0 for name in TRAYS}

        self.cubes = {}
        for name, ((x, y), color) in CUBES.items():
            self.cubes[name] = self.scene.add_entity(
                gs.morphs.Box(size=(CUBE_SIZE,) * 3, pos=(x, y, CUBE_SIZE / 2)),
                surface=gs.surfaces.Default(color=color),
            )

        self.franka = self.scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
        # 指示する人の目線に近い、ロボットの正面やや上から撮る
        self.cam = self.scene.add_camera(res=(1280, 720), pos=(2.5, 0.0, 1.5), lookat=(0.4, 0.0, 0.24), fov=33)
        self.scene.build()

        # 関節を目標角度に追従させる強さ（PD制御のゲイン）
        self.franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
        self.franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))
        self.franka.set_qpos(HOME)  # 真上に伸びた姿勢ではなく、作業しやすい構えから始める
        self.franka.control_dofs_position(HOME[:7], ARM)
        self.hand = self.franka.get_link("hand")
        self.gripping = False
        self.sim_time = 0.0  # シミュレーション内の経過秒数（＝動画の再生位置）

        if video_path:
            self.cam.start_recording(save_to_filename=video_path, fps=50)
        self.recording = bool(video_path)
        self.wait(50)  # ブロックが落ち着くのを待つ

    # ---- 基本動作 ----
    def step(self):
        if self.gripping:
            # 指を内側へ押す力をかけ続けて、ブロックを挟んだままにする
            self.franka.control_dofs_force(np.array([-GRIP_FORCE, -GRIP_FORCE]), FINGERS)
        else:
            self.franka.control_dofs_position(np.array([0.04, 0.04]), FINGERS)
        self.scene.step()
        self.sim_time += 0.01
        if self.recording:
            self.cam.render()

    def wait(self, steps):
        for _ in range(steps):
            self.step()

    def move_to(self, x, y, z, steps=120):
        """手先を (x, y, z) へ滑らかに動かす（IKの解まで関節角度を補間）。"""
        start = self.franka.get_dofs_position(ARM)
        goal = self.franka.inverse_kinematics(link=self.hand, pos=np.array([x, y, z]), quat=DOWN)[:7]
        for i in range(steps):
            t = (i + 1) / steps
            t = t * t * (3 - 2 * t)  # 動き始めと終わりをゆっくりにする
            self.franka.control_dofs_position(start + (goal - start) * t, ARM)
            self.step()
        self.wait(30)

    def grip(self):
        self.gripping = True
        self.wait(60)

    def release(self):
        self.gripping = False
        self.wait(50)

    # ---- タスク ----
    def cube_pos(self, name):
        return self.cubes[name].get_pos().cpu().numpy()

    def pick_and_place(self, cube, place):
        """ブロック cube をつかんで、place に置く。

        place がトレイ名（left / right）ならトレイの上に、ブロックの色（red など）ならそのブロックの上に積む。
        """
        cx, cy, cz = self.cube_pos(cube)  # 今ブロックがある場所を見てから取りに行く
        stacking = place in self.cubes
        if stacking:
            base_before = self.cube_pos(place)  # 土台のブロックの今の位置（あとで動いていないか確かめる）
            tx, ty, bz = base_before
            place_z = bz + CUBE_SIZE + HAND_OFFSET + 0.005  # 土台の上面にちょうど載る高さ
            print(f"[動作] {cube} のブロック ({cx:.2f}, {cy:.2f}) → {place} のブロックの上に積む")
        else:
            tx, ty = self.trays[place]
            tx += SLOTS[self.tray_count[place] % len(SLOTS)]  # トレイ上で、まだ置いていない場所を使う
            self.tray_count[place] += 1
            place_z = GRASP_Z + TRAY_HEIGHT + 0.01
            print(f"[動作] {cube} のブロック ({cx:.2f}, {cy:.2f}) → {place} のトレイ")

        self.move_to(cx, cy, LIFT_Z)                          # ブロックの真上へ
        self.move_to(cx, cy, cz + HAND_OFFSET, steps=80)      # 下ろす（積まれたブロックも、今の高さに合わせてつかむ）
        self.grip()                                           # つかむ
        self.move_to(cx, cy, LIFT_Z, steps=80)                # 持ち上げる
        # つかんだブロックが手の中心からずれていたら、その分だけ置く位置をずらす
        offset = self.cube_pos(cube)[:2] - self.hand.get_pos().cpu().numpy()[:2]
        tx, ty = tx - offset[0], ty - offset[1]
        self.move_to(tx, ty, LIFT_Z, steps=150)               # 置く場所の真上へ運ぶ
        self.move_to(tx, ty, place_z, steps=120 if stacking else 80)  # 積むときは、よりゆっくり下ろす
        self.release()                                        # 離す
        self.move_to(tx, ty, LIFT_Z, steps=80)                # 手を上げる

        x, y, z = self.cube_pos(cube)
        if stacking:
            bx, by, bz = self.cube_pos(place)
            base_kept = np.linalg.norm(self.cube_pos(place) - base_before) < 0.01  # 土台が押されて落ちていないか
            ok = base_kept and abs(x - bx) < CUBE_SIZE / 2 and abs(y - by) < CUBE_SIZE / 2 and z > bz + CUBE_SIZE * 0.8
        else:
            px, py = self.trays[place]
            ok = abs(x - px) < TRAY_SIZE / 2 and abs(y - py) < TRAY_SIZE / 2
        print(f"[結果] {cube} は ({x:.2f}, {y:.2f}, {z:.2f}) → {'成功' if ok else '失敗'}")
        return ok

    def reset_cubes(self, layout):
        """ブロックを新しい配置 {色: (x, y)} に置き直し、トレイを空にする。"""
        for name, (x, y) in layout.items():
            self.cubes[name].set_pos(np.array([x, y, CUBE_SIZE / 2]))
            self.cubes[name].set_quat(np.array([1.0, 0.0, 0.0, 0.0]))
        self.tray_count = {name: 0 for name in TRAYS}
        self.wait(50)

    def finish(self):
        if self.recording:
            self.cam.stop_recording()
