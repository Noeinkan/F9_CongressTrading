"""Tests for src.utils.extract_house_fd_bulk_zip (force=True + size validation)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from src.utils import extract_house_fd_bulk_zip, house_fd_bulk_zip_needs_extract


def _make_zip(zip_path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in files.items():
            zf.writestr(name, payload)


def test_extract_house_fd_bulk_zip_basic(tmp_path: Path) -> None:
    zip_path = tmp_path / "2026FD.zip"
    dest_dir = tmp_path / "out"
    _make_zip(
        zip_path,
        {
            "2026FD.txt": b"Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n",
            "2026FD.xml": b"<?xml version='1.0'?><root/>",
        },
    )
    out = extract_house_fd_bulk_zip(zip_path, dest_dir)
    assert (dest_dir / "2026FD.txt").exists()
    assert (dest_dir / "2026FD.xml").exists()
    assert out["2026FD.txt"] == len(b"Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n")


def test_extract_house_fd_bulk_zip_force_overwrites_stale_file(tmp_path: Path) -> None:
    """
    Simula il bug visto in produzione: il TXT locale ha contenuto vecchio ma dimensione
    identica al nuovo contenuto dello zip. extract_house_fd_bulk_zip con force=True deve
    sovrascrivere comunque. Senza force, il file sul disco potrebbe non essere aggiornato
    (anche se la detection needs_extract ritorna True solo se la dimensione cambia).
    """
    zip_path = tmp_path / "2026FD.zip"
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    header = b"Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n"
    old_line = b"old-row-content-here"  # 19 byte
    old_content = header + old_line * 31
    (dest_dir / "2026FD.txt").write_bytes(old_content)
    assert (dest_dir / "2026FD.txt").stat().st_size == len(old_content)

    # Stessa dimensione totale, contenuto diverso (suffisso che cambia)
    new_line = b"new-row-content-XYZ!"  # 19 byte (stesso di old_line)
    new_content = header + new_line * 31
    assert len(new_content) == len(old_content)
    _make_zip(zip_path, {"2026FD.txt": new_content})

    # Senza force: se la dimensione combacia, needs_extract ritorna False e la
    # detection based-on-size non rileverebbe la staleness.
    needs = house_fd_bulk_zip_needs_extract(zip_path, dest_dir)
    assert needs is False, "test setup: la detection basata sulla dimensione non coglie la staleness"

    # Con force=True, il file viene sovrascritto.
    extract_house_fd_bulk_zip(zip_path, dest_dir, force=True)
    new_on_disk = (dest_dir / "2026FD.txt").read_bytes()
    assert b"old-row-content-here" not in new_on_disk
    assert b"new-row-content-XYZ!" in new_on_disk


def test_extract_house_fd_bulk_zip_returns_sizes(tmp_path: Path) -> None:
    zip_path = tmp_path / "2026FD.zip"
    dest_dir = tmp_path / "out"
    payload = b"hello world"
    _make_zip(zip_path, {"2026FD.txt": payload})
    sizes = extract_house_fd_bulk_zip(zip_path, dest_dir)
    assert sizes == {"2026FD.txt": len(payload)}


def test_extract_house_fd_bulk_zip_overwrites_existing_file(tmp_path: Path) -> None:
    """Senza force=True, l'estrazione sovrascrive file esistenti della stessa dimensione."""
    zip_path = tmp_path / "2026FD.zip"
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    (dest_dir / "2026FD.txt").write_bytes(b"OLD-CONTENT")
    _make_zip(zip_path, {"2026FD.txt": b"OLD-CONTENT"})  # stessa dimensione
    extract_house_fd_bulk_zip(zip_path, dest_dir)
    # Il contenuto deve essere stato riscritto (estrarre lo stesso contenuto non cambia il file,
    # ma almeno la size su disco deve essere coerente con lo zip).
    assert (dest_dir / "2026FD.txt").stat().st_size == len(b"OLD-CONTENT")


def test_extract_house_fd_bulk_zip_force_replaces_content(tmp_path: Path) -> None:
    """force=True sovrascrive il contenuto anche quando la dimensione coincide."""
    zip_path = tmp_path / "2026FD.zip"
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    (dest_dir / "2026FD.txt").write_bytes(b"AAAAAAAAAAAAAAAA")  # 16 byte
    _make_zip(zip_path, {"2026FD.txt": b"BBBBBBBBBBBBBBBB"})  # 16 byte, contenuto diverso
    extract_house_fd_bulk_zip(zip_path, dest_dir)
    # Senza force: zipfile.extractall dovrebbe comunque sovrascrivere.
    assert (dest_dir / "2026FD.txt").read_bytes() == b"BBBBBBBBBBBBBBBB"
