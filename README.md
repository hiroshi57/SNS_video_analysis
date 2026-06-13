# SNS動画分析ツール

SNS(YouTube / Instagram / X / Facebook / TikTok)の動画やローカル動画ファイルを取り込み、
**要約・文字起こし・映像の特徴・映像の詳細・競合との差別化** を分析して動画とともに表示するツール。

Gemini APIのマルチモーダル動画理解を中核に、**Flash系で高速一次分析 → Pro系で深掘り**の2段構成。
分析結果はローカルに蓄積され、同ジャンルの過去動画と自動で競合比較される。

## フォルダ構成

```text
SNS_video_analysis/
├── app.py                  # Streamlit UI(エントリポイント)
│
├── src/                    # 分析エンジン
│   ├── config.py           #   設定(モデルID・パス・長尺分割の閾値)
│   ├── ingest.py           #   取込(YouTube URL直接 / yt-dlp DL / ファイル / Files API)
│   ├── analyze.py          #   Gemini呼び出し(Stage1高速 / Stage2深掘り / 長尺分割)
│   ├── store.py            #   SQLiteへの分析結果蓄積・履歴・同ジャンル検索
│   └── compare.py          #   過去分析との競合差別化比較
│
├── prompts/                # 分析プロンプト(観点を変えたい時はここを編集)
│   ├── stage1_fast.md      #   一次: 3行要約・ジャンルタグ・章立て・文字起こし
│   ├── stage2_visual.md    #   深掘り: 映像の特徴(フック/テロップ/編集)・シーン詳細
│   └── stage2_compare.md   #   競合差別化の比較
│
├── data/                   # 分析結果の蓄積(自動生成・git管理外)
│   ├── analyses.db         #   SQLite(全分析結果)
│   └── videos/             #   動画キャッシュ(DL・アップロードファイル)
│
├── docs/                   # 調査資料
│   └── SNS動画分析ツール比較_20260612.xlsx   # ツール選定の事前調査
│
├── Arc/                    # 使用済みSkillsの保管場所
│
├── requirements.txt        # Python依存パッケージ
├── .env.example            # 環境変数のテンプレート(コピーして .env を作る)
└── README.md
```

## セットアップ

```powershell
# 1. 依存パッケージをインストール
pip install -r requirements.txt

# 2. APIキーを設定(.env.example をコピーして編集)
Copy-Item .env.example .env
# .env を開いて GEMINI_API_KEY=... を記入(https://aistudio.google.com/apikey で取得)

# 3. (推奨) ffmpeg / ffprobe — ローカル動画の長さ検出・yt-dlpの結合に使用
winget install Gyan.FFmpeg
```

## 使い方

```powershell
python -m streamlit run app.py
```

1. ブラウザが開いたら、動画URLを入力するか動画ファイル(MP4/MOV/WebM等)をドラッグ&ドロップして「分析開始」
2. 数十秒で一次分析(3行要約・章立て・文字起こし)が表示される
3. 続けて映像分析(フック・テロップ・編集・シーン詳細)と競合比較がバックグラウンドで完了し、タブに反映される
4. サイドバーの履歴から過去の分析をいつでも再表示できる

### 取込パターン

| 入力 | 経路 |
| --- | --- |
| YouTube URL | Geminiが直接解析(ダウンロード不要・最速) |
| Instagram / X / Facebook / TikTok URL | yt-dlpでダウンロード → Files APIへアップロード |
| ローカルファイル(MP4/MOV/AVI/WMV/WebM/MKV等) | 20MB以下は直接送信、超過はFiles APIへアップロード |
| 長時間動画(90分超) | 時間オフセットで区間分割して分析 → 自動統合 |

### 競合比較のしくみ

分析のたびにジャンルタグ付きで結果がローカルDBに蓄積され、新しい動画を分析すると
**同ジャンルの過去分析(最大5件)** と自動比較して差別化ポイントの対比表を生成する。
蓄積が0件の間はジャンル一般の傾向との比較になり、蓄積が進むほど比較が具体的になる。

## 設定変更

- モデルの切替: `.env` に `MODEL_FAST` / `MODEL_DEEP` を指定(既定: gemini-2.5-flash / gemini-2.5-pro)
- 分析観点の変更: `prompts/` 配下のMarkdownを編集(コード変更不要)
- 長尺分割の閾値: [src/config.py](src/config.py)

## 制約

- 再生数・視聴者属性などの「視聴データ」は動画ファイルからは取得できない(各SNS公式アナリティクスの領域)
- Instagram / X / Facebook の非公開・ログイン必須動画は取込できない場合がある
