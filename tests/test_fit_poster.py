"""El cartel de la lista se sirve al ancho pedido, sin ampliar."""

from pathlib import Path

from PIL import Image

from app.services import image_store


def _jpeg(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (12, 40, 80)).save(path, format="JPEG", quality=90)


def test_fit_poster_shrinks_and_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "resolve_static_images_dir", lambda: tmp_path)
    event_id = "b" * 64
    filename = "00_bbbbbbbbbbbb.jpg"
    src = tmp_path / event_id / filename
    _jpeg(src, (2000, 1000))

    fitted = image_store.fit_poster(src, event_id, filename, 960)
    assert fitted != src
    with Image.open(fitted) as image:
        assert image.size == (960, 480)
        assert image.format == "JPEG"

    again = image_store.fit_poster(src, event_id, filename, 960)
    assert again == fitted
    assert fitted.stat().st_size < src.stat().st_size


def test_fit_poster_paints_transparency_on_white(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "resolve_static_images_dir", lambda: tmp_path)
    event_id = "d" * 64
    filename = "00_dddddddddddd.png"
    src = tmp_path / event_id / filename
    src.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    red = Image.new("RGBA", (1000, 1000), (200, 30, 30, 255))
    image.paste(red, (1000, 0))
    image.save(src, format="PNG")

    fitted = image_store.fit_poster(src, event_id, filename, 960)
    assert fitted != src
    with Image.open(fitted) as out:
        assert out.format == "JPEG"
        assert out.size == (960, 480)
        white = out.getpixel((40, 40))
        assert white[0] > 250 and white[1] > 250 and white[2] > 250
        tint = out.getpixel((900, 240))
        assert tint[0] > 150 and tint[1] < 80 and tint[2] < 80


def test_fit_poster_does_not_upscale(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "resolve_static_images_dir", lambda: tmp_path)
    event_id = "c" * 64
    filename = "00_cccccccccccc.jpg"
    src = tmp_path / event_id / filename
    _jpeg(src, (400, 225))

    assert image_store.fit_poster(src, event_id, filename, 960) == src
    assert not (tmp_path / ".derivatives").exists()
