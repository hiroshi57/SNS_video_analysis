"""動画の取り込み: URL判定 → YouTube直接参照 / yt-dlpダウンロード / ローカルファイル。

Geminiへの入力形式への変換(インライン / Files APIアップロード)もここで担う。
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from google.genai import types

from . import config

YOUTUBE_RE = re.compile(
    r"https?://(www\.|m\.)?(youtube\.com/(watch\?|shorts/|live/)|youtu\.be/)"
)

PLATFORM_PATTERNS = {
    "youtube": YOUTUBE_RE,
    "instagram": re.compile(r"https?://(www\.)?instagram\.com/"),
    "x": re.compile(r"https?://(www\.)?(x|twitter)\.com/"),
    "facebook": re.compile(r"https?://(www\.)?(facebook\.com|fb\.watch)/"),
    "tiktok": re.compile(r"https?://(www\.|vt\.)?tiktok\.com/"),
}

SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".wmv", ".webm", ".mkv", ".flv", ".mpeg", ".mpg", ".3gp"}


@dataclass
class VideoSource:
    kind: str  # "youtube_url" | "file"
    platform: str  # youtube / instagram / x / facebook / tiktok / web / local
    title: str
    source_url: str | None = None  # 元URL(st.video表示・記録用)
    local_path: Path | None = None
    duration_sec: float | None = None


def detect_platform(url: str) -> str:
    for name, pat in PLATFORM_PATTERNS.items():
        if pat.match(url):
            return name
    return "web"


# --- 結果キャッシュ用: ソースを一意に識別するキーを作る -------------------
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{6,})")
# 同じ動画でもURLに付きがちな追跡/付随パラメータ(これらが違うだけでは別物にしない)
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "si", "feature", "fbclid", "igshid", "gclid", "spm", "ref", "ref_src",
}


def _normalize_url(url: str) -> str:
    """同一動画を指すURLを正規化する(追跡パラメータ除去・YouTubeはID化)。"""
    u = url.strip()
    if YOUTUBE_RE.match(u):
        m = _YT_ID_RE.search(u)
        if m:
            return f"youtube:{m.group(1)}"
    parts = urlsplit(u)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = sorted((k, v) for k, v in parse_qsl(parts.query)
                   if k.lower() not in _TRACKING_PARAMS)
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"),
                       urlencode(query), ""))


def _file_quick_hash(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    """ファイル内容の高速ハッシュ。サイズ + 先頭/末尾チャンクで実用上一意。

    動画は数百MBになり得るため全体ハッシュは遅い。サイズと両端の
    チャンクを混ぜることで、高速かつ衝突しにくいキーにする。
    """
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk * 2:
            f.seek(-chunk, 2)
            h.update(f.read(chunk))
    return h.hexdigest()


def source_cache_key(source: str | Path) -> str:
    """URL/ファイルから、再分析スキップ用の安定したキーを生成する。"""
    if isinstance(source, str) and source.startswith("http"):
        return "url:" + _normalize_url(source)
    return "file:" + _file_quick_hash(Path(source))


def _ytdlp_info(url: str, download: bool) -> dict:
    """yt-dlpでメタデータ取得(download=Trueなら動画もキャッシュへ保存)。"""
    cmd = [
        sys.executable, "-m", "yt_dlp", "--no-playlist", "--print-json",
        "-f", "mp4/bestvideo*+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(config.VIDEO_CACHE_DIR / "%(id)s.%(ext)s"),
    ]
    # PATHに無くても見つけられた ffmpeg をyt-dlpに教える(映像+音声の結合に必要)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        cmd += ["--ffmpeg-location", ffmpeg]
    if not download:
        cmd.append("--skip-download")
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlpでの取得に失敗しました: {result.stderr[-500:]}")
    return json.loads(result.stdout.splitlines()[0])


@lru_cache(maxsize=1)
def _find_ffprobe() -> str | None:
    """ffprobe の実行パスを探す。PATH → imageio-ffmpeg同梱 の順。

    PATHに無くても、依存に入りがちな imageio-ffmpeg が同梱するバイナリを
    使えれば尺検出が動く。見つからなければ None(尺検出は諦める)。
    """
    found = shutil.which("ffprobe")
    if found:
        return found
    # imageio-ffmpeg は ffmpeg のみ同梱(ffprobeは無い)が、念のため確認する
    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        probe = str(Path(exe).with_name(
            "ffprobe.exe" if exe.lower().endswith(".exe") else "ffprobe"))
        if Path(probe).exists():
            return probe
    except Exception:  # noqa: BLE001 - 任意依存。無ければ無視
        pass
    return None


@lru_cache(maxsize=1)
def _find_ffmpeg() -> str | None:
    """ffmpeg の実行パスを探す。PATH → imageio-ffmpeg同梱 の順。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:  # noqa: BLE001
        pass
    return None


def _ffprobe_duration(path: Path) -> float | None:
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            return float(json.loads(result.stdout)["format"]["duration"])
    except (OSError, KeyError, ValueError):
        pass
    return None


def ingest(source: str | Path) -> VideoSource:
    """URLまたはローカルパスを受け取り、分析可能なVideoSourceにする。"""
    if isinstance(source, str) and source.startswith("http"):
        platform = detect_platform(source)
        if platform == "youtube" and config.YOUTUBE_DIRECT:
            # GeminiにYouTube URLを直接渡す(最速パスだが、AI Studioキーでは
            # file_uri取得が text/html で失敗することがある。既定は無効)
            try:
                info = _ytdlp_info(source, download=False)
                title = info.get("title") or source
                duration = info.get("duration")
            except (RuntimeError, FileNotFoundError, json.JSONDecodeError):
                title, duration = source, None
            return VideoSource(
                kind="youtube_url", platform=platform, title=title,
                source_url=source, duration_sec=duration,
            )
        # YouTubeを含む全URLをダウンロード → Files APIへ(確実な経路)
        info = _ytdlp_info(source, download=True)
        path = Path(info["filename"]) if "filename" in info else \
            config.VIDEO_CACHE_DIR / f"{info['id']}.{info.get('ext', 'mp4')}"
        if not path.exists():
            candidates = list(config.VIDEO_CACHE_DIR.glob(f"{info['id']}.*"))
            if not candidates:
                raise RuntimeError(f"ダウンロードファイルが見つかりません: {info['id']}")
            path = candidates[0]
        return VideoSource(
            kind="file", platform=platform, title=info.get("title") or source,
            source_url=source, local_path=path,
            duration_sec=info.get("duration") or _ffprobe_duration(path),
        )

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
        raise ValueError(f"未対応の動画形式です: {path.suffix}")
    return VideoSource(
        kind="file", platform="local", title=path.stem,
        local_path=path, duration_sec=_ffprobe_duration(path),
    )


def to_gemini_part(client, vs: VideoSource,
                   start_sec: float | None = None,
                   end_sec: float | None = None) -> types.Part:
    """VideoSourceをGeminiのcontents partへ変換する。

    start_sec/end_sec を渡すと video_metadata でその区間だけを解析対象にする
    (長尺動画のセグメント分析に使用。ffmpeg分割不要)。
    """
    video_metadata = None
    if start_sec is not None or end_sec is not None:
        video_metadata = types.VideoMetadata(
            start_offset=f"{int(start_sec or 0)}s",
            end_offset=f"{int(end_sec)}s" if end_sec is not None else None,
        )

    if vs.kind == "youtube_url":
        return types.Part(
            file_data=types.FileData(file_uri=vs.source_url),
            video_metadata=video_metadata,
        )

    path = vs.local_path
    mime = mimetypes.guess_type(str(path))[0] or "video/mp4"
    if path.stat().st_size <= config.INLINE_LIMIT_BYTES and video_metadata is None:
        return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)

    uploaded = _upload_and_wait(client, path, mime)
    return types.Part(
        file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type),
        video_metadata=video_metadata,
    )


_upload_cache: dict[str, object] = {}


def _upload_and_wait(client, path: Path, mime: str, timeout_sec: int = 600):
    """Files APIにアップロードしACTIVEになるまで待つ。同一セッション内は再利用。"""
    key = str(path.resolve())
    cached = _upload_cache.get(key)
    if cached is not None:
        return cached

    uploaded = client.files.upload(
        file=str(path), config=types.UploadFileConfig(mime_type=mime)
    )
    deadline = time.time() + timeout_sec
    while uploaded.state and uploaded.state.name == "PROCESSING":
        if time.time() > deadline:
            raise TimeoutError("Files APIの処理がタイムアウトしました")
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state and uploaded.state.name == "FAILED":
        raise RuntimeError("Files APIでの動画処理に失敗しました")
    _upload_cache[key] = uploaded
    return uploaded
