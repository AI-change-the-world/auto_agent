"""
Markdown 存储后端
"""

from pathlib import Path
from typing import Any


class MarkdownStorage:
    """Markdown 文件存储"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: str) -> None:
        """保存内容到文件"""
        file_path = self.storage_path / filename
        file_path.write_text(content, encoding="utf-8")

    def load(self, filename: str) -> str:
        """从文件加载内容"""
        file_path = self.storage_path / filename
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return ""

    def delete(self, filename: str) -> None:
        """删除文件"""
        file_path = self.storage_path / filename
        if file_path.exists():
            file_path.unlink()
