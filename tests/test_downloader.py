import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from src.downloader import fetch_focus


def _resp(status: int, content: bytes = b""):
    m = MagicMock()
    m.status_code = status
    m.content = content
    return m


PDF = b"%PDF-1.4 fake"


def test_download_on_first_try(tmp_path):
    with patch("src.downloader.DATA_DIR", tmp_path), \
         patch("src.downloader.requests.get", return_value=_resp(200, PDF)) as mock_get:
        result = fetch_focus(start=date(2026, 6, 22))

    assert result == tmp_path / "focus_2026-06-22.pdf"
    assert result.read_bytes() == PDF
    mock_get.assert_called_once()


def test_retries_on_404_and_finds_earlier_date(tmp_path):
    # segunda (22) e terça (23) falham; acha na segunda anterior (20)
    side_effects = [_resp(404), _resp(404), _resp(200, PDF)]
    with patch("src.downloader.DATA_DIR", tmp_path), \
         patch("src.downloader.requests.get", side_effect=side_effects):
        result = fetch_focus(start=date(2026, 6, 22))

    assert result.name == "focus_2026-06-20.pdf"
    assert result.read_bytes() == PDF


def test_raises_when_never_found(tmp_path):
    with patch("src.downloader.DATA_DIR", tmp_path), \
         patch("src.downloader.requests.get", return_value=_resp(404)):
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            fetch_focus(start=date(2026, 6, 22))


def test_skips_download_if_file_exists(tmp_path):
    existing = tmp_path / "focus_2026-06-22.pdf"
    existing.write_bytes(PDF)

    with patch("src.downloader.DATA_DIR", tmp_path), \
         patch("src.downloader.requests.get") as mock_get:
        result = fetch_focus(start=date(2026, 6, 22))

    mock_get.assert_not_called()
    assert result == existing


def test_network_error_continues_to_next_day(tmp_path):
    import requests as req
    side_effects = [req.ConnectionError("timeout"), _resp(200, PDF)]
    with patch("src.downloader.DATA_DIR", tmp_path), \
         patch("src.downloader.requests.get", side_effect=side_effects):
        result = fetch_focus(start=date(2026, 6, 22))

    assert result.name == "focus_2026-06-21.pdf"
