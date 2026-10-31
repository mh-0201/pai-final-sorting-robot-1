# ことばで指示する仕分けロボット

日本語で話しかけると、Mac上で動くローカルの言語モデルが指示をロボットの命令に変換し、
ロボットアーム（Franka Emika Panda）が**声で返事をしてから**、色ブロックをトレイへ仕分けたり、積み上げたりするシミュレーションです。
Physical AI 応用1講座 最終課題として作成しました。

- デモ動画: https://youtu.be/kmhiy8c1s0E　2分35秒・等倍速・音声あり
- シミュレータ: [Genesis](https://github.com/Genesis-Embodied-AI/Genesis) 1.4.5
- AI: [Ollama](https://ollama.com/) + qwen2.5:3b（推論のみ、学習なし）
- 音声: macOS の読み上げ機能（`say` コマンド）

最新版は [`v2_voice_stack/`](v2_voice_stack/) フォルダにあります。リポジトリ直下は、仕分けだけを行う最初の版（v1）です。

| 版 | できること | 場所 |
|---|---|---|
| **v2（最新・提出版）** | 仕分け ＋ **積み上げ** ＋ **声での会話** | [`v2_voice_stack/`](v2_voice_stack/) |
| v1 | トレイへの仕分け（字幕のみ） | リポジトリ直下 |

## しくみ

```
日本語の指示 ──▶ 言語モデル (qwen2.5:3b) ──▶ 命令 JSON ──▶ 声で返事 ──▶ 逆運動学 (IK) で動作
「その上に緑ものせて」          {"cube": "green", "place": "red"}   「緑のブロックを赤の上にのせます」
```

1. **指示の解釈（AI）** — [v2_voice_stack/ai_planner.py](v2_voice_stack/ai_planner.py)
   言語モデルに、使えるブロック（赤・緑・青）と置き場所（左=黄色・右=白のトレイ、またはほかのブロックの上）、
   現在の状況（まだ仕分けていないブロック、積み上げのいちばん上のブロック）を伝え、指示を命令の列に変換する。
   - 出力の形を JSON Schema で固定し、存在しない色や置き場所の命令は出せない。
   - 無い色（紫など）や関係のない指示には、命令を出さずに理由を返す。
   - 「その上」が指すブロックは小さなモデルには推理が難しいため、プログラムで計算してAIに伝える。
2. **声での会話** — [v2_voice_stack/make_video.py](v2_voice_stack/make_video.py)
   指示は人らしい声（Kyoko）、ロボットの返事は機械らしい声（Rocko）で読み上げ、「人が話す → ロボットが返事 → 動く」の流れにする。
3. **動作の実行（ロボット）** — [v2_voice_stack/robot.py](v2_voice_stack/robot.py)
   ブロックの現在位置を読み取り、IKで手先を真上 → つかむ高さ → 持ち上げ → 置く場所の上 → 置く高さ、と順に動かす。
   - 積み上げでは、土台のブロックの今の高さから置く高さを計算し、ゆっくり下ろす。
   - つかむ力を 3N に調整し、持ち上げた直後に「手の中心からのずれ」を測って置く位置を補正する。
   - 置いたあと、トレイの上にあるか／土台を落とさずに積めたかを自動で判定する。

左右は「ロボットの正面に立って指示する人」から見た向きで定義しており、動画の画面の左右とも一致する。

## 結果（v2）

- 言い回しを変えた13通りの指示の変換テスト: **13/13 正解**（[test_planner.py](v2_voice_stack/test_planner.py)）
- デモ動画の3場面・7つの指示で、**8/8 回成功**（うち積み上げ 2/2 回、3段のタワー）。紫のブロックの指示には動かずに声で「ありません」と返答。

## 動かし方（Apple Silicon の Mac で確認）

[uv](https://docs.astral.sh/uv/) と [Ollama](https://ollama.com/) を使います。

```bash
brew install uv ollama
ollama pull qwen2.5:3b   # 言語モデル（約1.9GB）をダウンロード
cd v2_voice_stack
uv sync                  # Python 3.11 と Genesis などをインストール
```

別のターミナルで `ollama serve` を起動したまま、次を実行します。

```bash
uv run python test_planner.py   # AIの変換テスト
uv run python make_video.py     # 録画して、音声・字幕付きの動画（final_video.mp4）を作る
```

`make_video.py` は字幕に macOS のヒラギノフォント、音声に macOS の `say` コマンドを使います。
1つ上のフォルダに講座の OP・ED 動画（`PAI応用1_最終課題_OP.mp4` / `_ED.mp4`）があれば、それを前後に付けた YouTube 用の動画も作ります（動画ファイルはリポジトリに含めていません）。

## ファイル構成

| ファイル | 内容 |
|---|---|
| [v2_voice_stack/robot.py](v2_voice_stack/robot.py) | シーン（アーム・色ブロック・トレイ・カメラ）と、仕分け・積み上げ動作 |
| [v2_voice_stack/ai_planner.py](v2_voice_stack/ai_planner.py) | 日本語の指示を言語モデルで命令 JSON に変換 |
| [v2_voice_stack/make_video.py](v2_voice_stack/make_video.py) | デモの録画と、音声・字幕・OP/ED付きの動画編集 |
| [v2_voice_stack/test_planner.py](v2_voice_stack/test_planner.py) | 指示の変換テスト |
| [v2_voice_stack/report/](v2_voice_stack/report/) | 説明資料（レポート）の元ファイル |
| リポジトリ直下の `*.py` | v1（仕分けのみ）と、段階的に作った途中のスクリプト（環境確認 → IK → ピック＆プレース → AI） |

## 今後の展望

- カメラ画像からブロックの位置や色を認識する（今はシミュレータから位置を直接読んでいる）
- 音声認識（Whisper など）で、マイクに本当に話しかけて操作する
- 「いちばん上に青を積んで」のような言い回しの取り違えを、例やテストを増やして減らす
- 実機（SO-101 など）での動作
