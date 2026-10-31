"""環境の動作確認: Frankaアームと立方体を置き、アームを少し動かして動画に保存する。"""
import numpy as np
import genesis as gs

# M1 Mac では gpu を指定すると Metal（Apple の GPU）が使われる
gs.init(backend=gs.gpu, logging_level="warning")

scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=0.01))
scene.add_entity(gs.morphs.Plane())
scene.add_entity(gs.morphs.Box(size=(0.04, 0.04, 0.04), pos=(0.65, 0.0, 0.02)))
franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))

cam = scene.add_camera(res=(640, 480), pos=(3.0, -1.0, 1.5), lookat=(0.5, 0.0, 0.3), fov=30)
scene.build()

# 関節を目標角度へ動かす（7関節 + 指2本）
target = np.array([0.0, 0.4, 0.0, -2.0, 0.0, 2.4, 0.8, 0.04, 0.04])
cam.start_recording(save_to_filename="check_env.mp4", fps=50)
for i in range(300):
    franka.control_dofs_position(target * min(i / 150, 1.0))
    scene.step()
    cam.render()
cam.stop_recording()
print("OK: check_env.mp4 を保存しました")
