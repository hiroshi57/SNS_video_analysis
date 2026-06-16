"""設定: モデルID・パス・閾値。環境変数(.env)で上書き可能。"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # SNS_video_analysis/
# override=True: .env を設定の正典にする。これがないと、シェルやOSに残った
# 古い GEMINI_API_KEY 等のシステム環境変数が .env より優先され、
# 無効キーで「API key not valid(400)」になる事故が起きる。
load_dotenv(PROJECT_ROOT / ".env", override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# 一次分析(速度重視) / 深掘り分析(品質重視)
# 既定は両方 flash。Pro は無料枠が 0 のため、課金を有効化した環境でのみ
# .env で MODEL_DEEP=gemini-2.5-pro として品質を上げる運用にする。
MODEL_FAST = os.getenv("MODEL_FAST", "gemini-2.5-flash")
MODEL_DEEP = os.getenv("MODEL_DEEP", "gemini-2.5-flash")

# YouTube URLをGeminiへ直接渡すか。AI Studioキーでは file_uri 取得が
# text/html で失敗することがあるため既定は無効(ダウンロード経路を使う)。
# 確実に直接解析できる環境では .env で YOUTUBE_DIRECT=1 にすると最速になる。
YOUTUBE_DIRECT = os.getenv("YOUTUBE_DIRECT", "0") == "1"

DATA_DIR = PROJECT_ROOT / "data"
VIDEO_CACHE_DIR = DATA_DIR / "videos"
DB_PATH = DATA_DIR / "analyses.db"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Gemini インライン送信の上限(これ以下はFiles APIを使わず直接送る)
INLINE_LIMIT_BYTES = 19 * 1024 * 1024

# この秒数を超える動画は低解像度メディア設定でトークンを節約する
LOW_RES_THRESHOLD_SEC = 30 * 60

# この秒数を超える動画は「速度優先モード」に切り替える。
# 速度優先では、全文逐語の文字起こしを省いて要約・章立てを優先し、
# 映像深掘りも代表シーンに絞ることで長尺でも待ち時間を抑える。
FAST_MODE_THRESHOLD_SEC = int(os.getenv("FAST_MODE_THRESHOLD_SEC", str(10 * 60)))

# この秒数を超える動画はセグメント分割して分析→統合する(時間オフセット)
SEGMENT_THRESHOLD_SEC = 90 * 60
SEGMENT_LENGTH_SEC = 45 * 60

DATA_DIR.mkdir(exist_ok=True)
VIDEO_CACHE_DIR.mkdir(exist_ok=True)
