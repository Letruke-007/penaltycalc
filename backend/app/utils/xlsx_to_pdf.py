from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    pass


def convert_xlsx_to_pdf(xlsx_path: Path) -> Path:
    """
    Convert XLSX -> PDF using headless LibreOffice (soffice).
    Output PDF is created next to XLSX and cached (if exists, returned as-is).
    """
    xlsx_path = Path(xlsx_path)

    if not xlsx_path.exists():
        raise PdfConversionError(f"XLSX not found: {xlsx_path}")

    # output рядом с xlsx
    pdf_path = xlsx_path.with_suffix(".pdf")
    if pdf_path.exists():
        return pdf_path

    soffice = shutil.which("soffice")
    if not soffice:
        raise PdfConversionError("LibreOffice (soffice) is not installed in runtime image")

    outdir = str(xlsx_path.parent)

    # отдельный профиль LO, чтобы избежать блокировок в контейнере/параллельных запросов
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        cmd = [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to",
            "pdf",
            "--outdir",
            outdir,
            str(xlsx_path),
        ]

        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise PdfConversionError(f"LibreOffice convert failed: {p.stderr.strip() or p.stdout.strip()}")

    if not pdf_path.exists():
        raise PdfConversionError("PDF was not created")

    return pdf_path
