from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


class ArchiveError(RuntimeError):
    pass


class ArchiveManager:
    """Validate and safely extract user-selected ZIP archives."""

    SUPPORTED_SUFFIXES = {".zip"}

    @classmethod
    def supported(cls, path: str | Path) -> bool:
        return Path(path).suffix.lower() in cls.SUPPORTED_SUFFIXES

    @staticmethod
    def _safe_parts(name: str) -> tuple[str, ...]:
        normalized = name.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or not path.parts:
            raise ArchiveError(f"Güvensiz arşiv yolu: {name}")
        if any(part in ("", ".", "..") for part in path.parts):
            raise ArchiveError(f"Güvensiz arşiv yolu: {name}")
        if ":" in path.parts[0]:
            raise ArchiveError(f"Güvensiz arşiv yolu: {name}")
        return tuple(path.parts)

    @classmethod
    def _validate_info(cls, info: zipfile.ZipInfo) -> tuple[str, ...]:
        parts = cls._safe_parts(info.filename)
        if info.flag_bits & 0x1:
            raise ArchiveError("Şifreli ZIP arşivleri otomatik çıkarılamıyor.")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(unix_mode) == stat.S_IFLNK:
            raise ArchiveError(f"Sembolik link içeren ZIP reddedildi: {info.filename}")
        return parts

    @classmethod
    def inspect(cls, archive_path: str | Path) -> dict:
        archive = Path(archive_path).expanduser().resolve()
        if not archive.is_file():
            raise ArchiveError("Arşiv dosyası bulunamadı.")
        if not cls.supported(archive):
            raise ArchiveError(f"Bu sürüm yalnızca ZIP destekliyor: {archive.suffix or 'uzantısız'}")

        try:
            with zipfile.ZipFile(archive, "r") as handle:
                infos = handle.infolist()
                if not infos:
                    raise ArchiveError("ZIP arşivi boş.")
                file_count = 0
                total_size = 0
                compressed_size = 0
                top_levels = set()
                for info in infos:
                    parts = cls._validate_info(info)
                    top_levels.add(parts[0])
                    if not info.is_dir():
                        file_count += 1
                        total_size += int(info.file_size)
                        compressed_size += int(info.compress_size)
                bad = handle.testzip()
                if bad:
                    raise ArchiveError(f"ZIP CRC testi başarısız: {bad}")
        except ArchiveError:
            raise
        except (zipfile.BadZipFile, EOFError, OSError) as exc:
            raise ArchiveError(f"ZIP doğrulanamadı: {exc}") from exc

        return {
            "archive_path": str(archive),
            "archive_name": archive.name,
            "file_count": file_count,
            "uncompressed_bytes": total_size,
            "compressed_bytes": compressed_size,
            "single_root": next(iter(top_levels)) if len(top_levels) == 1 else None,
        }

    @staticmethod
    def default_destination(archive_path: str | Path) -> Path:
        archive = Path(archive_path).expanduser().resolve()
        candidate = archive.parent / archive.stem
        index = 1
        while candidate.exists():
            suffix = "-extracted" if index == 1 else f"-extracted-{index}"
            candidate = archive.parent / f"{archive.stem}{suffix}"
            index += 1
        return candidate

    @classmethod
    def extract(
        cls,
        archive_path: str | Path,
        destination: str | Path | None = None,
        progress: Callable[[int, int], None] | None = None,
        verified_info: dict | None = None,
    ) -> dict:
        info = dict(verified_info) if verified_info is not None else cls.inspect(archive_path)
        archive = Path(info["archive_path"]).expanduser().resolve()
        target_root = Path(destination).expanduser().resolve() if destination else cls.default_destination(archive)

        if target_root.exists():
            raise ArchiveError("Çıkarma hedefi zaten var; mevcut dosyaların üzerine yazılmadı.")

        parent = target_root.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            free = shutil.disk_usage(parent).free
        except OSError as exc:
            raise ArchiveError(f"Boş disk alanı okunamadı: {exc}") from exc
        required = int(info["uncompressed_bytes"])
        if free < required:
            raise ArchiveError(
                f"Yetersiz disk alanı. Gerekli: {required} bayt, boş: {free} bayt."
            )

        extracted = 0
        target_root.mkdir(parents=False, exist_ok=False)
        try:
            with zipfile.ZipFile(archive, "r") as handle:
                for member in handle.infolist():
                    parts = cls._validate_info(member)
                    target = target_root.joinpath(*parts)
                    target_resolved = target.resolve()
                    try:
                        common = os.path.commonpath((str(target_root), str(target_resolved)))
                    except ValueError as exc:
                        raise ArchiveError(f"Güvensiz arşiv yolu: {member.filename}") from exc
                    if common != str(target_root):
                        raise ArchiveError(f"Güvensiz arşiv yolu: {member.filename}")

                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue

                    target.parent.mkdir(parents=True, exist_ok=True)
                    with handle.open(member, "r") as source, target.open("wb") as output:
                        while True:
                            block = source.read(1024 * 1024)
                            if not block:
                                break
                            output.write(block)
                            extracted += len(block)
                            if progress:
                                progress(extracted, max(1, required))

            if progress:
                progress(required, max(1, required))
        except Exception:
            shutil.rmtree(target_root, ignore_errors=True)
            raise

        game_root = target_root
        single_root = info.get("single_root")
        if single_root:
            candidate = target_root / single_root
            if candidate.is_dir():
                game_root = candidate

        return {
            **info,
            "destination": str(target_root),
            "game_root": str(game_root),
            "extracted_bytes": required,
        }
