# backend/queue_manager.py
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class QueueItem:
    id: str
    url: str
    title: str = ""
    channel: str = ""
    format_id: str = "mp4"
    quality: str = "Melhor"
    status: str = "queued"   # queued | downloading | done | error
    progress: float = 0.0
    speed: str = ""
    error: str = ""
    output_dir: str = ""

class DownloadQueue:
    def __init__(self):
        self._items: dict[str, QueueItem] = {}
        self._lock = asyncio.Lock()

    async def add(self, item_id: str, req):
        async with self._lock:
            self._items[item_id] = QueueItem(
                id=item_id, url=req.url,
                format_id=req.format_id, quality=req.quality,
                output_dir=req.output_dir,
            )

    async def update(self, item_id: str, **kwargs):
        async with self._lock:
            item = self._items.get(item_id)
            if item:
                for k, v in kwargs.items():
                    setattr(item, k, v)

    async def remove(self, item_id: str):
        async with self._lock:
            self._items.pop(item_id, None)

    def items(self) -> list[dict]:
        return [asdict(i) for i in self._items.values()]
