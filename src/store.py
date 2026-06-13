"""分析結果のSQLite永続化・履歴一覧・同ジャンル検索。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    duration_sec REAL,
    genre_tags TEXT NOT NULL DEFAULT '[]',
    stage1_json TEXT,
    stage2_json TEXT,
    compare_json TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def save_analysis(vs, stage1: dict) -> int:
    """Stage 1完了時点でレコードを作成しIDを返す。"""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO analyses (created_at, title, platform, source_url,"
            " local_path, duration_sec, genre_tags, stage1_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                vs.title, vs.platform, vs.source_url,
                str(vs.local_path) if vs.local_path else None,
                vs.duration_sec,
                json.dumps(stage1.get("genre_tags", []), ensure_ascii=False),
                json.dumps(stage1, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def update_stage2(analysis_id: int, stage2: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE analyses SET stage2_json = ? WHERE id = ?",
            (json.dumps(stage2, ensure_ascii=False), analysis_id),
        )


def update_compare(analysis_id: int, compare: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE analyses SET compare_json = ? WHERE id = ?",
            (json.dumps(compare, ensure_ascii=False), analysis_id),
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["genre_tags"] = json.loads(d["genre_tags"] or "[]")
    for key in ("stage1_json", "stage2_json", "compare_json"):
        d[key] = json.loads(d[key]) if d[key] else None
    return d


def get_analysis(analysis_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_analyses(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def find_same_genre(genre_tags: list[str], exclude_id: int,
                    limit: int = 5) -> list[dict]:
    """ジャンルタグが1つでも重なる過去分析を新しい順に返す。"""
    if not genre_tags:
        return []
    tags = {t.strip().lower() for t in genre_tags}
    matches = []
    for item in list_analyses(limit=200):
        if item["id"] == exclude_id or not item["stage1_json"]:
            continue
        item_tags = {t.strip().lower() for t in item["genre_tags"]}
        if tags & item_tags:
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches
