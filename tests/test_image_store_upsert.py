"""save_image must not pass raw JPEG bytes through aiomysql query % args."""

from pathlib import Path

import pytest

from app.services import image_store

pytestmark = pytest.mark.asyncio


class FakeDb:
    def __init__(self):
        self.inserts: list[tuple[str, tuple]] = []

    async def execute_insert(self, query, params=None):
        self.inserts.append((query, params or ()))
        return 0


async def test_save_image_uses_hex_and_row_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "resolve_static_images_dir", lambda: Path(tmp_path))
    event_id = "a" * 64
    filename = "00_aaaaaaaaaaaa.jpg"
    content = b"\xff\xd8\xff%jpeg"

    db = FakeDb()
    url = await image_store.save_image(db, event_id, filename, content)

    assert url.endswith(f"{event_id}/{filename}")
    assert (tmp_path / event_id / filename).read_bytes() == content
    assert len(db.inserts) == 1
    sql, params = db.inserts[0]
    assert "UNHEX(%s)" in sql
    assert "AS incoming" in sql
    assert "VALUES(" not in sql.split("ON DUPLICATE KEY UPDATE", 1)[1]
    assert params[0] == event_id
    assert params[1] == filename
    assert params[2] == content.hex()
    assert isinstance(params[2], str)
    assert params[4] == len(content)
