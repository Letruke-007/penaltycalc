from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..extract.errors import ExtractError
from .pdf_to_json import pdf_to_json


@dataclass
class BatchItemResult:
    pdf: str
    ok: bool
    error: Optional[str] = None
    out_json: Optional[str] = None


def run_single(pdf_path: str, out_json_path: str, category: Optional[str] = None) -> Dict:
    data = pdf_to_json(pdf_path, category=category)
    p = Path(out_json_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def run_batch(pdf_dir: str, out_dir: str, category: Optional[str] = None) -> Dict:
    src = Path(pdf_dir)
    dst = Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)

    pdfs = sorted([p for p in src.rglob("*.pdf") if p.is_file()])

    items: List[BatchItemResult] = []
    for p in pdfs:
        out_json = dst / f"{p.stem}.json"
        try:
            run_single(str(p), str(out_json), category=category)
            items.append(BatchItemResult(pdf=str(p), ok=True, out_json=str(out_json)))

        except ExtractError as e:
            # КРИТИЧНО: если JSON уже был — удаляем, чтобы не залип старый
            if out_json.exists():
                out_json.unlink()

            items.append(BatchItemResult(pdf=str(p), ok=False, error=str(e)))

        except Exception as e:
            if out_json.exists():
                out_json.unlink()

            items.append(BatchItemResult(pdf=str(p), ok=False, error=f"Unhandled: {e}"))

    report = {
        "pdf_dir": str(src),
        "out_dir": str(dst),
        "count_total": len(items),
        "count_ok": sum(1 for x in items if x.ok),
        "count_fail": sum(1 for x in items if not x.ok),
        "items": [x.__dict__ for x in items],
    }

    (dst / "batch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


class PipelineOrchestrator:
    """
    Совместимость с существующими тестами проекта.

    Минимальная обёртка вокруг функций pdf_to_json/run_single/run_batch,
    без архитектурных изменений.
    """

    def __init__(self) -> None:
        pass

    # --- legacy API (пока не реализовано, тесты ожидают NotImplementedError) ---

    async def execute(self, pdf_path) -> None:
        """
        Legacy method ожидается тестами как async и пока должна быть не реализована.
        """
        raise NotImplementedError

    def validate_input(self, pdf_path) -> None:
        """
        Legacy method ожидается тестами и пока должна быть не реализована.
        """
        raise NotImplementedError

    # --- текущий рабочий API для этапа PDF -> JSON ---

    def process_pdf(self, pdf_path: str, *, category: Optional[str] = None) -> Dict:
        return pdf_to_json(pdf_path, category=category)

    def save_json(self, data: Dict, out_json_path: str) -> None:
        p = Path(out_json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def process_and_save(self, pdf_path: str, out_json_path: str, *, category: Optional[str] = None) -> Dict:
        data = self.process_pdf(pdf_path, category=category)
        self.save_json(data, out_json_path)
        return data

    def process_dir(self, pdf_dir: str, out_dir: str, *, category: Optional[str] = None) -> Dict:
        return run_batch(pdf_dir, out_dir, category=category)
