# ことばで指示する仕分けロボット

日本語の指示（例:「赤いブロックを黄色いトレイに入れて」）を、Mac上で動くローカルの言語モデルがロボットの命令に変換し、
ロボットアーム（Franka Emika Panda）が色ブロックをトレイへ仕分けるシミュレーションです。
Physical AI 応用1講座 最終課題として作成しました。

- デモ動画: （YouTubeのURLをここに書く）
- シミュレータ: [Genesis](https://github.com/Genesis-Embodied-AI/Genesis) 1.4.5
- AI: [Ollama](https://ollama.com/) + qwen2.5:3b（推論のみ、学習なし）

## しくみ

```
日本語の指示 ──▶ 言語モデル (qwen2.5:3b) ──▶ 命令 JSON ──▶ 逆運動学 (IK) ──▶ つかむ → 運ぶ → 置く
「赤を黄色いトレイへ」               {"cube": "red", "tray": "left"}
```

1. **指示の解釈（AI）** — [ai_planner.py](ai_planner.py)
   言語モデルに、使えるブロック（赤・緑・青）とトレイ（左=黄色・右=白）、まだ仕分けていないブロックを伝え、指示を命令の列に変換する。
   出力の形を JSON Schema で固定しているため、存在しない色やトレイの命令は出せない。
   無い色（紫など）や関係のない指示には、命令を出さずに理由を返す。
2. **動作の実行（ロボット）** — [robot.py](robot.py)
   ブロックの現在位置を読み取り、IKで手先を真上 → つかむ高さ → 持ち上げ → トレイの上 → 置く、と順に動かす。
   つかんでいる間は指に力をかけ続けて落とさないようにし、同じトレイに置くときは位置をずらす。
   置いたあと、ブロックがトレイの上にあるかを自動で判定する。

左右は「ロボットの正面に立って指示する人」から見た向きで定義しており、動画の画面の左右とも一致する。

## 結果

- 言い回しを変えた8通りの指示の変換テスト: **8/8 正解**（[test_planner.py](test_planner.py)）
- デモ動画の2場面・5つの指示で、仕分け **6/6 回成功**。紫のブロックの指示には動かずに「ありません」と返答。

## 動かし方（Apple Silicon の Mac で確認）

[uv](https://docs.astral.sh/uv/) と [Ollama](https://ollama.com/) を使います。

```bash
brew install uv ollama
uv sync                  # Python 3.11 と Genesis などをインストール
ollama pull qwen2.5:3b   # 言語モデル（約1.9GB）をダウンロード
```

別のターミナルで `ollama serve` を起動したまま、次を実行します。

```bash
uv run python step4_ai_sort.py --interactive  # 自分で指示を打ち込んで動かす
uv run python make_video.py                   # デモ動画（final_video.mp4）を作る
```

`make_video.py` は字幕に macOS のヒラギノフォントを使います。

## ファイル構成

| ファイル | 内容 |
|---|---|
| [robot.py](robot.py) | シーン（アーム・色ブロック・トレイ・カメラ）と、ピック＆プレース動作 |
| [ai_planner.py](ai_planner.py) | 日本語の指示を言語モデルで命令 JSON に変換 |
| [make_video.py](make_video.py) | デモの録画と、タイトル・字幕付きの動画編集 |
| [step4_ai_sort.py](step4_ai_sort.py) | AIとロボットをつないだ本体（デモ／対話モード） |
| [test_planner.py](test_planner.py) | 指示の変換テスト |
| [check_env.py](check_env.py), [step2_ik.py](step2_ik.py), [step3_pick_place.py](step3_pick_place.py) | 段階的に作った途中のスクリプト（環境確認 → IK → ピック＆プレース） |
| [video_log.json](video_log.json) | デモ動画での指示・AIの返事・動作のタイミングの記録 |

## 今後の展望

- カメラ画像からブロックの位置や色を認識する（今はシミュレータから位置を直接読んでいる）
- 「積み上げて」「並べて」など、指示できる動作の種類を増やす
- 実機（SO-101 など）での動作
