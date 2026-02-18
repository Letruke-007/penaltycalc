from __future__ import annotations

import sys
from pathlib import Path

import pytest


def pytest_sessionstart(session):
    """
    Гарантируем, что backend/ (где лежит пакет app/) есть в sys.path,
    даже если pytest запущен из корня репозитория.
    """
    backend_dir = Path(__file__).resolve().parents[1]  # .../backend
    p = str(backend_dir)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """
    Общий фикстурный PDF для legacy-тестов, которые проверяют NotImplemented.
    Берём первый PDF из tests/fixtures/pdf.
    """
    pdf_dir = fixtures_dir / "pdf"
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        pytest.skip(f"No PDF fixtures found in {pdf_dir}")
    return pdfs[0]


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """
    Временная папка для тестов batch/вывода.
    """
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out
