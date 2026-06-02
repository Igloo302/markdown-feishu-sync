#!/usr/bin/env python3
"""
同步状态管理工具
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
import hashlib


SYNC_STATE_PATH = Path(__file__).resolve().parent.parent / "sync_state.json"


@dataclass
class SyncRecord:
    feishu_doc_id: str
    obsidian_path: str
    feishu_title: str
    last_sync_time: str
    obsidian_hash: str
    feishu_hash: str
    sync_direction: str = "bidirectional"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> "SyncRecord":
        return cls(
            feishu_doc_id=doc_id,
            obsidian_path=data.get("obsidian_path", ""),
            feishu_title=data.get("feishu_title", ""),
            last_sync_time=data.get("last_sync_time", ""),
            obsidian_hash=data.get("obsidian_hash", ""),
            feishu_hash=data.get("feishu_hash", ""),
            sync_direction=data.get("sync_direction", "bidirectional")
        )


class SyncStateManager:
    """同步状态管理器"""

    def __init__(self, state_path: Path = SYNC_STATE_PATH):
        self.state_path = state_path
        self._state: dict = {}
        self._load()

    def _load(self):
        """加载状态"""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {}
        else:
            self._state = {}

    def _save(self):
        """保存状态"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get_all(self) -> list[SyncRecord]:
        """获取所有同步记录"""
        return [
            SyncRecord.from_dict(doc_id, data)
            for doc_id, data in self._state.items()
        ]

    def get_by_feishu_id(self, doc_id: str) -> Optional[SyncRecord]:
        """通过飞书文档 ID 获取记录"""
        if doc_id in self._state:
            return SyncRecord.from_dict(doc_id, self._state[doc_id])
        return None

    def get_by_obsidian_path(self, path: str) -> Optional[SyncRecord]:
        """通过 Obsidian 路径获取记录"""
        for doc_id, data in self._state.items():
            if data.get("obsidian_path") == path:
                return SyncRecord.from_dict(doc_id, data)
        return None

    def upsert(self, record: SyncRecord):
        """创建或更新记录"""
        self._state[record.feishu_doc_id] = record.to_dict()
        self._save()

    def remove(self, doc_id: str) -> bool:
        """移除记录"""
        if doc_id in self._state:
            del self._state[doc_id]
            self._save()
            return True
        return False

    def remove_by_path(self, path: str) -> bool:
        """通过 Obsidian 路径移除记录"""
        for doc_id, data in self._state.items():
            if data.get("obsidian_path") == path:
                del self._state[doc_id]
                self._save()
                return True
        return False

    def update_hashes(self, doc_id: str, obsidian_hash: str, feishu_hash: str):
        """更新哈希值"""
        if doc_id in self._state:
            self._state[doc_id]["obsidian_hash"] = obsidian_hash
            self._state[doc_id]["feishu_hash"] = feishu_hash
            self._state[doc_id]["last_sync_time"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def update_path(self, doc_id: str, new_path: str):
        """更新 Obsidian 路径（文档移动时使用）"""
        if doc_id in self._state:
            self._state[doc_id]["obsidian_path"] = new_path
            self._save()

    def count(self) -> int:
        """获取记录数量"""
        return len(self._state)


if __name__ == "__main__":
    # 测试
    manager = SyncStateManager()
    print(f"当前同步记录数: {manager.count()}")

    # 列出所有记录
    for record in manager.get_all():
        print(f"  {record.feishu_doc_id}: {record.feishu_title} -> {record.obsidian_path}")