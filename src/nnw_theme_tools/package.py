from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .project import ThemeError
from .validate import validate_archive, validate_source

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def archive_bytes(theme: Path, *, allow_remote_media: bool = False) -> tuple[bytes, list[str]]:
    """Build the deterministic ZIP. The only place package validation runs."""
    source_report = validate_source(theme, allow_remote_media=allow_remote_media)
    source_report.require_ok()
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(theme.iterdir(), key=lambda item: item.name):
            info = zipfile.ZipInfo(f"{theme.name}/{path.name}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes())
    content = output.getvalue()
    archive_report = validate_archive(content, f"{theme.name}.zip")
    archive_report.require_ok()
    return content, source_report.warnings + archive_report.warnings


def build_archive(
    theme: Path, output_dir: Path, *, allow_remote_media: bool = False
) -> tuple[Path, list[str]]:
    content, warnings = archive_bytes(theme, allow_remote_media=allow_remote_media)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{theme.name}.zip"
    destination.write_bytes(content)
    if not destination.name.endswith(".nnwtheme.zip"):
        raise ThemeError("internal error: package has an invalid release asset name")
    return destination, warnings
