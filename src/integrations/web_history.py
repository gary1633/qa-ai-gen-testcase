"""Lịch sử hội thoại của Web GUI (SQLite): tìm lại cuộc trò chuyện cũ và tiếp tục sau khi server khởi động lại.

Mỗi hội thoại lưu: chủ sở hữu (mã trình duyệt), tiêu đề, trạng thái, văn bản phục vụ tìm kiếm, bản chụp
`QASession.snapshot()` và toàn bộ sự kiện chat (để hiển thị lại y nguyên). File Excel của từng hội thoại nằm
riêng trong `files/<id>.xlsx` nên hội thoại khác cùng tên tính năng không ghi đè.
"""
import json
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    search_text TEXT NOT NULL DEFAULT '',
    snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations (owner, updated_at DESC);
CREATE TABLE IF NOT EXISTS events (
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (conversation_id, seq)
);
"""


def fold_text(text: str) -> str:
    """Chuẩn hóa để tìm kiếm không phân biệt hoa/thường và dấu tiếng Việt ('chuyen tien' khớp 'Chuyển tiền')."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").casefold()


class HistoryStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.files_dir = self.root / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "history.db"
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def excel_path(self, conversation_id: str) -> str:
        return str(self.files_dir / f"{conversation_id}.xlsx")

    def save_conversation(
        self,
        conversation_id: str,
        owner: str,
        title: str,
        status: str,
        search_text: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Tạo/cập nhật hội thoại. `snapshot=None` giữ nguyên bản chụp phiên đã lưu."""
        now = time.time()
        snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None
        with self._db() as db:
            db.execute(
                """INSERT INTO conversations (id, owner, title, status, created_at, updated_at, search_text, snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     title = excluded.title, status = excluded.status, updated_at = excluded.updated_at,
                     search_text = excluded.search_text, snapshot = COALESCE(excluded.snapshot, conversations.snapshot)""",
                (conversation_id, owner, title, status, now, now, search_text, snapshot_json),
            )

    def append_event(self, conversation_id: str, event: Dict[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO events (conversation_id, seq, payload) VALUES (?, ?, ?)",
                (conversation_id, event["id"], json.dumps(event, ensure_ascii=False)),
            )

    def load(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._db() as db:
            row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                return None
            events = [
                json.loads(r["payload"])
                for r in db.execute("SELECT payload FROM events WHERE conversation_id = ? ORDER BY seq", (conversation_id,))
            ]
        return {
            "id": row["id"],
            "owner": row["owner"],
            "title": row["title"],
            "search_text": row["search_text"],
            "snapshot": json.loads(row["snapshot"]) if row["snapshot"] else None,
            "events": events,
        }

    def list_conversations(self, owner: str, query: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        """Hội thoại của một trình duyệt, mới nhất trước; `query` khớp mọi từ (không dấu) trong tiêu đề/nội dung."""
        terms = fold_text(query).split()
        with self._db() as db:
            rows = db.execute(
                "SELECT id, title, status, created_at, updated_at, search_text FROM conversations "
                "WHERE owner = ? ORDER BY updated_at DESC",
                (owner,),
            ).fetchall()
        result = []
        for row in rows:
            haystack = fold_text(f"{row['title']}\n{row['search_text']}")
            if all(t in haystack for t in terms):
                result.append({k: row[k] for k in ("id", "title", "status", "created_at", "updated_at")})
                if len(result) >= limit:
                    break
        return result
