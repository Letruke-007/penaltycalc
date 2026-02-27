# backend/app/services/processing_service.py

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectResult:
    debtor_name: str
    debtor_inn: str


class ProcessingService:
    """
    Facade for the deterministic pipeline:
      - inspect (preview or internal)
      - PDF -> JSON (Statement)
      - JSON -> XLSX

    IMPORTANT SEMANTICS:
      - inspect endpoint is UX preview
      - process MUST re-run full pipeline (force=True)
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[1] / "data"
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def new_batch_id(self) -> str:
        return uuid.uuid4().hex

    # -----------------------------
    # Inspect (text-layer only)
    # -----------------------------
    def ensure_inspect(
        self, pdf_path: Path, inspect_path: Path, *, force: bool
    ) -> InspectResult:
        if not force and inspect_path.exists():
            try:
                payload = json.loads(inspect_path.read_text(encoding="utf-8"))
                return InspectResult(
                    debtor_name=str(payload.get("debtor_name", "")),
                    debtor_inn=str(payload.get("debtor_inn", "")),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("inspect.json invalid, recomputing: %s", e)

        result = self._inspect_pdf(pdf_path)
        inspect_path.write_text(
            json.dumps(
                {"debtor_name": result.debtor_name, "debtor_inn": result.debtor_inn},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return result

    def _inspect_pdf(self, pdf_path: Path) -> InspectResult:
        try:
            import fitz  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise ProcessingError(f"PyMuPDF (fitz) is required: {e}") from e

        # Read ALL pages to avoid picking supplier/header noise from page 1 only.
        doc = fitz.open(pdf_path)
        try:
            all_text_parts: list[str] = []
            for pno in range(doc.page_count):
                page = doc.load_page(pno)
                all_text_parts.append(page.get_text("text") or "")
            full_text = "\n".join(all_text_parts)
        finally:
            doc.close()

        lines = [ln.strip() for ln in full_text.splitlines() if ln and ln.strip()]

        # Use parser-grade inspect (same rules as statement_parser bottom-block/header)
        try:
            from app.extract.parsers.statement_inspect import inspect_statement  # type: ignore

            payload = inspect_statement(
                lines,
                source_pdf=str(pdf_path),
                filename=pdf_path.name,
            )
            debtor = payload.get("debtor") or {}
            name = str(debtor.get("name") or "").strip()
            inn = str(debtor.get("inn") or "").strip()
            return InspectResult(debtor_name=name, debtor_inn=inn)
        except Exception as e:  # noqa: BLE001
            # Fallback: keep previous behavior only if parser-inspect fails unexpectedly
            import re

            inn = ""
            m = re.search(r"ИНН\s*[:№]?\s*(\d{10}|\d{12})", full_text)
            if m:
                inn = m.group(1)
            else:
                m2 = re.search(r"\b(\d{10}|\d{12})\b", full_text)
                inn = m2.group(1) if m2 else ""

            # conservative fallback name: first non-trivial line
            name = ""
            for ln in lines[:40]:
                low = ln.lower()
                if len(ln) >= 8 and not low.startswith(
                    ("справка", "задолж", "итого", "оплата", "выставлен")
                ):
                    name = ln
                    break

            return InspectResult(debtor_name=name, debtor_inn=inn)

    # -----------------------------
    # Pipeline: PDF -> JSON -> XLSX
    # -----------------------------
    async def process_pdf_to_xlsx(
        self,
        pdf_path: Path,
        json_out: Path,
        xlsx_out: Path,
        *,
        calc_date: str,
        category: str,
        rate_percent: float,
        overdue_start_day: int,
        exclude_zero_debt_periods: bool = False,
        add_state_duty: bool = False,
    ) -> None:
        statement_obj = await self._pdf_to_json(
            pdf_path=pdf_path,
            calc_date=calc_date,
            category=category,
            rate_percent=rate_percent,
            overdue_start_day=overdue_start_day,
            exclude_zero_debt_periods=exclude_zero_debt_periods,
            add_state_duty=add_state_duty,
        )

        json_out.write_text(
            json.dumps(statement_obj, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        await self._json_to_xlsx(
            json_path=json_out, xlsx_path=xlsx_out, add_state_duty=add_state_duty
        )

    async def process_pdf_to_json(
        self,
        pdf_path: Path,
        json_out: Path,
        *,
        calc_date: str,
        category: str,
        rate_percent: float,
        overdue_start_day: int,
        exclude_zero_debt_periods: bool = False,
        add_state_duty: bool = False,
    ) -> None:
        """PDF -> JSON only (used for merged XLSX path)."""
        statement_obj = await self._pdf_to_json(
            pdf_path=pdf_path,
            calc_date=calc_date,
            category=category,
            rate_percent=rate_percent,
            overdue_start_day=overdue_start_day,
            exclude_zero_debt_periods=exclude_zero_debt_periods,
            add_state_duty=add_state_duty,
        )
        json_out.write_text(
            json.dumps(statement_obj, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    async def _pdf_to_json(
        self,
        *,
        pdf_path: Path,
        calc_date: str,
        category: str,
        rate_percent: float,
        overdue_start_day: int,
        exclude_zero_debt_periods: bool = False,
        add_state_duty: bool = False,
    ) -> dict[str, Any]:
        try:
            from app.pipeline.pdf_to_json import pdf_to_json  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise ProcessingError(
                f"Cannot import app.pipeline.pdf_to_json.pdf_to_json: {e}"
            ) from e

        res = pdf_to_json(
            str(pdf_path),
            calc_date=calc_date,
            category=category,
            rate_percent=rate_percent,
            overdue_start_day=overdue_start_day,
        )

        if isinstance(res, dict):
            st = res.get("statement")
            if isinstance(st, dict):
                st.setdefault(
                    "exclude_zero_debt_periods", bool(exclude_zero_debt_periods)
                )
            return res

        if hasattr(res, "model_dump"):
            return res.model_dump(exclude_none=True)
        raise ProcessingError("pdf_to_json returned unsupported type")

    async def _json_to_xlsx(
        self, *, json_path: Path, xlsx_path: Path, add_state_duty: bool = False
    ) -> None:
        try:
            from app.pipeline.json_to_xlsx import json_to_xlsx  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise ProcessingError(
                f"Cannot import app.pipeline.json_to_xlsx.json_to_xlsx: {e}"
            ) from e

        json_to_xlsx(json_path, xlsx_path, add_state_duty=add_state_duty)

    async def jsons_to_merged_xlsx(
        self, json_paths: list[Path], xlsx_path: Path, add_state_duty: bool = False
    ) -> None:
        """Build ONE XLSX from multiple per-contract Statement JSON files."""
        try:
            from app.pipeline.json_to_xlsx import build_xlsx_from_many_statement_jsons  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise ProcessingError(
                f"Cannot import app.pipeline.json_to_xlsx.build_xlsx_from_many_statement_jsons: {e}"
            ) from e

        build_xlsx_from_many_statement_jsons(
            [Path(p) for p in json_paths],
            Path(xlsx_path),
            add_state_duty=add_state_duty,
        )

    async def json_to_xlsx(
        self, *, json_path: Path, xlsx_path: Path, add_state_duty: bool = False
    ) -> None:
        """JSON -> XLSX (public helper, used by batch merge mode)."""
        await self._json_to_xlsx(
            json_path=json_path, xlsx_path=xlsx_path, add_state_duty=add_state_duty
        )
