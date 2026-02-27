# backend/app/api/batches.py

from __future__ import annotations

import json
import logging
import csv
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.services.processing_service import ProcessingError, ProcessingService
from app.utils.xlsx_to_pdf import PdfConversionError, convert_xlsx_to_pdf
from app.core.errors import UserFacingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batches", tags=["batches"])


# ---- Strict Contracts (NO alias/fallback) ----


class ItemCalcParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calc_date: str = Field(..., min_length=1)  # DD.MM.YYYY
    category: str = Field(..., min_length=1)

    rate_percent: float
    overdue_day: int  # 1..31
    exclude_zero_debt_periods: bool
    add_state_duty: bool


class ProcessItemMeta(BaseModel):
    """
    Per-file processing parameters coming from frontend as items_meta (JSON array).

    STRICT:
      - no alias (file_name only)
      - no optional fields
      - extra=forbid
    """

    model_config = ConfigDict(extra="forbid")

    client_file_id: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)

    calc_date: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)

    rate_percent: float
    overdue_day: int
    exclude_zero_debt_periods: bool
    add_state_duty: bool


class CreateBatchProcessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str


class DebtorPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    inn: Optional[str] = None


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    client_file_id: str
    file_name: str

    status: str  # PENDING | INSPECTED | PROCESSING | DONE | ERROR
    error: Optional[str] = None
    # Optional structured error (safe to show in UI)
    error_code: Optional[str] = None
    error_stage: Optional[str] = None
    error_details: Optional[dict[str, Any]] = None

    debtor: DebtorPreview
    params: ItemCalcParams

    json_path: Optional[str] = None
    xlsx_path: Optional[str] = None


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    status: str  # RUNNING | DONE | ERROR
    created_at: str  # ISO

    total_items: int
    done_items: int
    error_items: int

    items: list[BatchItem]
    error: Optional[str] = None

    # Optional merged output (when several PDFs belong to one debtor)
    merge_enabled: bool = False
    merge_status: Optional[str] = None  # MERGED | SKIPPED | ERROR
    merge_warning: Optional[str] = None
    merge_error: Optional[str] = None
    merged_xlsx_path: Optional[str] = None
    merged_manifest_path: Optional[str] = None


# ---- Batch diagnostics (structured per-file report) ----


@dataclass
class BatchDiagRecord:
    # identity
    file_name: str
    client_file_id: str
    item_id: str

    # status
    status: str  # ok | error
    stage: str  # inspect | pdf_to_json | json_to_xlsx | merged_xlsx | done | error
    elapsed_ms: int

    # extracted meta (best-effort)
    debtor_name: Optional[str] = None
    debtor_inn: Optional[str] = None

    # counts (best-effort)
    charges_count: Optional[int] = None
    payments_count: Optional[int] = None
    months_count: Optional[int] = None

    # paths (relative to data dir)
    pdf_path: Optional[str] = None
    inspect_path: Optional[str] = None
    json_path: Optional[str] = None
    xlsx_path: Optional[str] = None

    # error info (only for status=error)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    traceback: Optional[str] = None


def _diag_paths(batch_dir: Path) -> tuple[Path, Path]:
    return (batch_dir / "batch_diagnostics.json", batch_dir / "batch_diagnostics.csv")


def _write_diag(batch_dir: Path, records: list[BatchDiagRecord]) -> None:
    json_p, csv_p = _diag_paths(batch_dir)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(records),
        "ok": sum(1 for r in records if r.status == "ok"),
        "error": sum(1 for r in records if r.status == "error"),
        "records": [r.__dict__ for r in records],
    }
    json_p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # CSV (flat) for quick review
    fieldnames = [
        "file_name",
        "client_file_id",
        "item_id",
        "status",
        "stage",
        "elapsed_ms",
        "debtor_inn",
        "debtor_name",
        "months_count",
        "charges_count",
        "payments_count",
        "pdf_path",
        "inspect_path",
        "json_path",
        "xlsx_path",
        "error_type",
        "error_message",
    ]
    with csv_p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            row = {k: getattr(r, k, None) for k in fieldnames}
            w.writerow(row)


def _exc_payload(e: BaseException) -> tuple[str, str, str]:
    return (
        type(e).__name__,
        str(e),
        "".join(traceback.format_exception(type(e), e, e.__traceback__)),
    )


def _user_error_text(e: BaseException) -> str:
    """Короткий человекочитаемый текст для UI."""
    if isinstance(e, UserFacingError):
        return e.message
    s = str(e) or type(e).__name__
    # чтобы не раздувать batch.json и UI
    if len(s) > 4000:
        s = s[:4000] + "…"
    return s


def _user_error_payload(
    e: BaseException,
) -> tuple[str, Optional[str], Optional[str], Optional[dict[str, Any]]]:
    """
    Normalize exception to user-facing text + optional structured fields.
    Returns: (message, code, stage, details)
    """
    if isinstance(e, UserFacingError):
        return (e.message, e.code, e.stage, e.details or None)
    # Fallback (keep it deterministic and short)
    msg = str(e) or type(e).__name__
    if len(msg) > 5000:
        msg = msg[:5000] + "…"
    return (msg, None, None, None)


@dataclass(frozen=True)
class BatchPaths:
    batch_dir: Path
    batch_json: Path


def _paths(svc: ProcessingService, batch_id: str) -> BatchPaths:
    batch_dir = svc.data_dir / "batches" / batch_id
    return BatchPaths(
        batch_dir=batch_dir,
        batch_json=batch_dir / "batch.json",
    )


def _load_batch(batch_json: Path) -> Batch:
    data = json.loads(batch_json.read_text(encoding="utf-8"))
    return Batch.model_validate(data)


def _save_batch(batch_json: Path, batch: Batch) -> None:
    payload = batch.model_dump(exclude_none=True)
    batch_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _recount(batch: Batch) -> None:
    batch.total_items = len(batch.items)
    batch.done_items = sum(1 for it in batch.items if it.status == "DONE")
    batch.error_items = sum(1 for it in batch.items if it.status == "ERROR")


def _normalize_inn(v: Optional[str]) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _normalize_name(v: Optional[str]) -> str:
    """Lightweight, dependency-free name normalization for merge check."""
    s = (v or "").strip().upper()
    if not s:
        return ""
    for q in ['"', "«", "»"]:
        s = s.replace(q, "")
    # collapse whitespace and punctuation
    for bad in ["\\", "/", ":", "*", "?", "<", ">", "|", ",", ";"]:
        s = s.replace(bad, " ")
    s = " ".join(s.split())
    return s


def _can_merge_debtors(items: list[BatchItem]) -> tuple[bool, Optional[str]]:
    """Return (can_merge, reason_if_cannot).

    Priority:
      - if there are 2+ non-empty INNs and they differ -> cannot merge
      - else if INN is missing, fallback to normalized name; if 2+ non-empty names and differ -> cannot merge
      - if we cannot establish any comparable key (all empty) -> cannot merge
    """
    inns = sorted(
        {_normalize_inn(it.debtor.inn) for it in items if _normalize_inn(it.debtor.inn)}
    )
    if len(inns) >= 2:
        return False, f"Разные ИНН в пакете: {', '.join(inns)}"
    if len(inns) == 1:
        return True, None

    names = sorted(
        {
            _normalize_name(it.debtor.name)
            for it in items
            if _normalize_name(it.debtor.name)
        }
    )
    if len(names) >= 2:
        return (
            False,
            "Разные наименования должника в пакете (ИНН отсутствует/не распознан)",
        )
    if len(names) == 1:
        return True, None

    return (
        False,
        "Не удалось определить должника (нет ИНН и наименования) — объединение отключено",
    )


@router.post("/process", response_model=CreateBatchProcessResponse)
async def process_batch(
    files: list[UploadFile] = File(...),
    items_meta: str = Form(...),
    merge_xlsx: bool = Form(True),
) -> CreateBatchProcessResponse:
    svc = ProcessingService()
    batch_id = svc.new_batch_id()
    bp = _paths(svc, batch_id)
    bp.batch_dir.mkdir(parents=True, exist_ok=True)

    # Parse items_meta STRICTLY
    try:
        meta_list = TypeAdapter(list[ProcessItemMeta]).validate_json(items_meta)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail=f"items_meta must be JSON array of ProcessItemMeta: {e}",
        ) from e

    meta_by_name = {m.file_name: m for m in meta_list}

    # Init batch state (STRICT fields present from the start)
    now_iso = datetime.now(timezone.utc).isoformat()
    items: list[BatchItem] = []
    for f in files:
        if not f.filename:
            raise HTTPException(
                status_code=422, detail="uploaded file has empty filename"
            )

        if f.filename not in meta_by_name:
            raise HTTPException(
                status_code=422,
                detail=f"items_meta missing entry for file_name='{f.filename}'",
            )

        meta = meta_by_name[f.filename]

        item_id = f"{batch_id}:{f.filename}"
        items.append(
            BatchItem(
                item_id=item_id,
                client_file_id=meta.client_file_id,
                file_name=meta.file_name,
                status="PENDING",
                debtor=DebtorPreview(name=None, inn=None),
                params=ItemCalcParams(
                    calc_date=meta.calc_date,
                    category=meta.category,
                    rate_percent=meta.rate_percent,
                    overdue_day=meta.overdue_day,
                    exclude_zero_debt_periods=meta.exclude_zero_debt_periods,
                    add_state_duty=meta.add_state_duty,
                ),
            )
        )

    batch = Batch(
        batch_id=batch_id,
        status="RUNNING",
        created_at=now_iso,
        total_items=len(items),
        done_items=0,
        error_items=0,
        items=items,
        merge_enabled=bool(merge_xlsx),
    )
    _save_batch(bp.batch_json, batch)

    diag_records: list[BatchDiagRecord] = []
    diag_json, diag_csv = _diag_paths(bp.batch_dir)
    # Write empty diagnostics early so UI/users can see progress even if crash happens
    _write_diag(bp.batch_dir, diag_records)

    try:
        # -------------------------------------------------
        # 1) Persist + inspect all PDFs (per-file)
        # -------------------------------------------------
        pdf_paths: list[Path] = []
        inspect_paths: list[Path] = []
        json_paths: list[Path] = []

        for i, f in enumerate(files):
            t0 = time.perf_counter()
            item = batch.items[i]
            pdf_path = bp.batch_dir / item.file_name
            inspect_path = bp.batch_dir / f"{item.file_name}.inspect.json"
            json_out = bp.batch_dir / f"{item.file_name}.json"

            pdf_paths.append(pdf_path)
            inspect_paths.append(inspect_path)
            json_paths.append(json_out)

            content = await f.read()
            pdf_path.write_bytes(content)

            item.status = "INSPECTED"
            _recount(batch)
            _save_batch(bp.batch_json, batch)

            ir = svc.ensure_inspect(
                pdf_path=pdf_path, inspect_path=inspect_path, force=True
            )
            item.debtor = DebtorPreview(
                name=(ir.debtor_name or None), inn=(ir.debtor_inn or None)
            )
            _save_batch(bp.batch_json, batch)

            rec = BatchDiagRecord(
                file_name=item.file_name,
                client_file_id=item.client_file_id,
                item_id=item.item_id,
                status="ok",
                stage="inspect",
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                debtor_name=item.debtor.name,
                debtor_inn=item.debtor.inn,
                pdf_path=str(pdf_path.relative_to(svc.data_dir)),
                inspect_path=str(inspect_path.relative_to(svc.data_dir)),
            )
            diag_records.append(rec)
            _write_diag(bp.batch_dir, diag_records)

        # -------------------------------------------------
        # 2) Decide whether we can merge
        # -------------------------------------------------
        do_merge = bool(merge_xlsx) and len(batch.items) > 1
        if do_merge:
            can_merge, reason = _can_merge_debtors(batch.items)
            if not can_merge:
                batch.merge_status = "SKIPPED"
                batch.merge_warning = (
                    reason or "Объединение невозможно"
                ) + "; сформированы отдельные XLSX по каждой справке"
                do_merge = False

        # -------------------------------------------------
        # 3A) Merge path: PDF -> JSON per file, then 1 XLSX from all JSONs
        # -------------------------------------------------
        if do_merge:
            batch.merge_status = None
            batch.merge_warning = None
            batch.merge_error = None
            _save_batch(bp.batch_json, batch)

            for i, item in enumerate(batch.items):
                t0 = time.perf_counter()
                item.status = "PROCESSING"
                _recount(batch)
                _save_batch(bp.batch_json, batch)

                xlsx_out = bp.batch_dir / f"{item.file_name}.xlsx"

                try:
                    await svc.process_pdf_to_json(
                        pdf_path=pdf_paths[i],
                        json_out=json_paths[i],
                        calc_date=item.params.calc_date,
                        category=item.params.category,
                        rate_percent=item.params.rate_percent,
                        overdue_start_day=item.params.overdue_day,
                        exclude_zero_debt_periods=item.params.exclude_zero_debt_periods,
                        add_state_duty=item.params.add_state_duty,
                    )

                    # per-item XLSX ALWAYS (even in merge mode)
                    await svc.json_to_xlsx(
                        json_path=json_paths[i],
                        xlsx_path=xlsx_out,
                        add_state_duty=item.params.add_state_duty,
                    )

                    item.status = "DONE"
                    item.json_path = str(json_paths[i].relative_to(svc.data_dir))
                    item.xlsx_path = str(xlsx_out.relative_to(svc.data_dir))

                except Exception as e:  # noqa: BLE001
                    # per-item error; continue processing next files
                    msg, code, stage, details = _user_error_payload(e)

                    item.status = "ERROR"
                    item.error = msg
                    item.error_code = code
                    item.error_stage = stage
                    item.error_details = details

                    err_type, _, err_tb = _exc_payload(e)
                    for r in diag_records:
                        if r.item_id == item.item_id:
                            r.status = "error"
                            r.stage = "error"
                            r.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                            r.error_type = err_type
                            r.error_message = msg
                            r.traceback = err_tb
                            break
                    _write_diag(bp.batch_dir, diag_records)
                    _recount(batch)
                    _save_batch(bp.batch_json, batch)
                    continue

                # diagnostics: update record for this file
                try:
                    # best-effort counts from produced JSON
                    js = json.loads(json_paths[i].read_text(encoding="utf-8"))
                    charges_count = len(
                        js.get("statement", {}).get("charges", []) or []
                    )
                    payments_count = len(
                        js.get("statement", {}).get("payments", []) or []
                    )
                    months = {
                        c.get("period")
                        for c in (js.get("statement", {}).get("charges", []) or [])
                        if c.get("period")
                    }
                    months_count = len(months)
                except Exception:  # noqa: BLE001
                    charges_count = payments_count = months_count = None

                for r in diag_records:
                    if r.item_id == item.item_id:
                        r.status = "ok"
                        r.stage = "json_to_xlsx"
                        r.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        r.xlsx_path = str(xlsx_out.relative_to(svc.data_dir))
                        r.charges_count = charges_count
                        r.payments_count = payments_count
                        r.months_count = months_count
                        break
                _write_diag(bp.batch_dir, diag_records)
                _recount(batch)
                _save_batch(bp.batch_json, batch)

            # If any item failed, skip merge but keep per-item XLSX
            if any(it.status == "ERROR" for it in batch.items):
                batch.merge_status = "SKIPPED"
                batch.merge_warning = "Объединение не выполнено: есть ошибки в одном или нескольких файлах; сформированы отдельные XLSX по каждой справке"
                batch.status = "DONE"
                _recount(batch)
                _save_batch(bp.batch_json, batch)
                return CreateBatchProcessResponse(batch_id=batch_id)

            merged_xlsx = bp.batch_dir / "merged.xlsx"
            merged_manifest = bp.batch_dir / "merged.manifest.json"
            merged_manifest.write_text(
                json.dumps(
                    {
                        "batch_id": batch_id,
                        "files": [it.file_name for it in batch.items],
                        "jsons": [str(p.name) for p in json_paths],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            try:
                await svc.jsons_to_merged_xlsx(
                    json_paths,
                    merged_xlsx,
                    add_state_duty=any(it.params.add_state_duty for it in batch.items),
                )
            except Exception as e:  # noqa: BLE001
                batch.merge_status = "SKIPPED"
                batch.merge_warning = "Ошибка формирования объединённого XLSX; сформированы отдельные XLSX по каждой справке"
                batch.merge_error = _user_error_text(e)
                batch.status = "DONE"
                _recount(batch)
                _save_batch(bp.batch_json, batch)
                return CreateBatchProcessResponse(batch_id=batch_id)

            diag_records.append(
                BatchDiagRecord(
                    file_name="__MERGED__",
                    client_file_id="__MERGED__",
                    item_id=f"{batch_id}:__MERGED__",
                    status="ok",
                    stage="merged_xlsx",
                    elapsed_ms=0,
                    pdf_path=None,
                    inspect_path=None,
                    json_path=None,
                    xlsx_path=str(merged_xlsx.relative_to(svc.data_dir)),
                )
            )
            _write_diag(bp.batch_dir, diag_records)

            batch.merge_status = "MERGED"
            batch.merged_xlsx_path = str(merged_xlsx.relative_to(svc.data_dir))
            batch.merged_manifest_path = str(merged_manifest.relative_to(svc.data_dir))

            batch.status = "DONE"
            _recount(batch)
            _save_batch(bp.batch_json, batch)

        # -------------------------------------------------
        # 3B) Non-merge path (legacy): per-file PDF -> JSON -> XLSX
        # -------------------------------------------------
        else:
            for i, item in enumerate(batch.items):
                t0 = time.perf_counter()
                pdf_path = pdf_paths[i]
                json_out = json_paths[i]
                xlsx_out = bp.batch_dir / f"{item.file_name}.xlsx"

                item.status = "PROCESSING"
                _recount(batch)
                _save_batch(bp.batch_json, batch)

                try:
                    await svc.process_pdf_to_xlsx(
                        pdf_path=pdf_path,
                        json_out=json_out,
                        xlsx_out=xlsx_out,
                        calc_date=item.params.calc_date,
                        category=item.params.category,
                        rate_percent=item.params.rate_percent,
                        overdue_start_day=item.params.overdue_day,
                        exclude_zero_debt_periods=item.params.exclude_zero_debt_periods,
                        add_state_duty=item.params.add_state_duty,
                    )
                except Exception as e:  # noqa: BLE001
                    # per-item error, continue with next file
                    msg, code, stage, details = _user_error_payload(e)

                    item.status = "ERROR"
                    item.error = msg
                    item.error_code = code
                    item.error_stage = stage
                    item.error_details = details

                    err_type, err_msg, err_tb = _exc_payload(e)
                    # update diagnostics record for this item
                    for r in diag_records:
                        if r.item_id == item.item_id:
                            r.status = "error"
                            r.stage = "error"
                            r.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                            r.error_type = err_type
                            r.error_message = msg
                            r.traceback = err_tb
                            break
                    _write_diag(bp.batch_dir, diag_records)
                    _recount(batch)
                    _save_batch(bp.batch_json, batch)
                    continue

                # diagnostics: update record for this file (best-effort counts from produced JSON)
                try:
                    js = json.loads(json_out.read_text(encoding="utf-8"))
                    charges_count = len(
                        js.get("statement", {}).get("charges", []) or []
                    )
                    payments_count = len(
                        js.get("statement", {}).get("payments", []) or []
                    )
                    months = {
                        c.get("period")
                        for c in (js.get("statement", {}).get("charges", []) or [])
                        if c.get("period")
                    }
                    months_count = len(months)
                except Exception:  # noqa: BLE001
                    charges_count = payments_count = months_count = None

                # find existing inspect record; if absent, create one
                rec = None
                for r in diag_records:
                    if r.item_id == item.item_id:
                        rec = r
                        break
                if rec is None:
                    rec = BatchDiagRecord(
                        file_name=item.file_name,
                        client_file_id=item.client_file_id,
                        item_id=item.item_id,
                        status="ok",
                        stage="json_to_xlsx",
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                        debtor_name=item.debtor.name,
                        debtor_inn=item.debtor.inn,
                        pdf_path=str(pdf_path.relative_to(svc.data_dir)),
                        inspect_path=(
                            str(
                                (
                                    bp.batch_dir / f"{item.file_name}.inspect.json"
                                ).relative_to(svc.data_dir)
                            )
                            if (
                                bp.batch_dir / f"{item.file_name}.inspect.json"
                            ).exists()
                            else None
                        ),
                    )
                    diag_records.append(rec)

                rec.status = "ok"
                rec.stage = "json_to_xlsx"
                rec.elapsed_ms = int((time.perf_counter() - t0) * 1000)
                rec.json_path = str(json_out.relative_to(svc.data_dir))
                rec.xlsx_path = str(
                    (bp.batch_dir / f"{item.file_name}.xlsx").relative_to(svc.data_dir)
                )
                rec.charges_count = charges_count
                rec.payments_count = payments_count
                rec.months_count = months_count
                _write_diag(bp.batch_dir, diag_records)
                item.status = "DONE"
                item.json_path = str(json_out.relative_to(svc.data_dir))
                item.xlsx_path = str(xlsx_out.relative_to(svc.data_dir))
                _recount(batch)
                _save_batch(bp.batch_json, batch)

            batch.status = "DONE"
            _recount(batch)
            _save_batch(bp.batch_json, batch)

    except HTTPException:
        batch.status = "ERROR"
        _recount(batch)
        _save_batch(bp.batch_json, batch)
        raise
    except (ProcessingError, Exception) as e:  # noqa: BLE001
        logger.exception("Batch processing failed: %s", e)
        user_msg, user_code, user_stage, user_details = _user_error_payload(e)

        # diagnostics: mark the first non-done item as error
        err_type, err_msg, err_tb = _exc_payload(e)
        for it in batch.items:
            if it.status in ("PENDING", "INSPECTED", "PROCESSING"):
                # find or create record for this item
                rec = None
                for r in diag_records:
                    if r.item_id == it.item_id:
                        rec = r
                        break
                if rec is None:
                    rec = BatchDiagRecord(
                        file_name=it.file_name,
                        client_file_id=it.client_file_id,
                        item_id=it.item_id,
                        status="error",
                        stage="error",
                        elapsed_ms=0,
                        debtor_name=it.debtor.name,
                        debtor_inn=it.debtor.inn,
                    )
                    diag_records.append(rec)

                rec.status = "error"
                rec.stage = "error"
                rec.error_type = err_type
                rec.error_message = user_msg
                rec.traceback = err_tb
                break
        _write_diag(bp.batch_dir, diag_records)
        batch.status = "ERROR"
        batch.error = user_msg

        for it in batch.items:
            if it.status in ("PENDING", "INSPECTED", "PROCESSING"):
                it.status = "ERROR"
                it.error = user_msg
                it.error_code = user_code
                it.error_stage = user_stage
                it.error_details = user_details
                break

        _recount(batch)
        _save_batch(bp.batch_json, batch)
        return CreateBatchProcessResponse(batch_id=batch_id)

    _write_diag(bp.batch_dir, diag_records)

    return CreateBatchProcessResponse(batch_id=batch_id)


@router.get("/{batch_id}", response_model=Batch)
async def get_batch(batch_id: str) -> Batch:
    svc = ProcessingService()
    bp = _paths(svc, batch_id)
    if not bp.batch_json.exists():
        raise HTTPException(status_code=404, detail="batch not found")
    return _load_batch(bp.batch_json)


@router.get("/{batch_id}/download/xlsx")
async def download_batch_xlsx(batch_id: str) -> Any:
    """Download merged XLSX, if present.

    This endpoint is used by frontend when the user enabled "merge".
    """
    svc = ProcessingService()
    bp = _paths(svc, batch_id)
    if not bp.batch_json.exists():
        raise HTTPException(status_code=404, detail="batch not found")

    batch = _load_batch(bp.batch_json)
    if batch.merge_status != "MERGED" or not batch.merged_xlsx_path:
        # Keep deterministic behaviour: merged file exists only on successful merge.
        detail = batch.merge_warning or "merged XLSX not available"
        raise HTTPException(status_code=404, detail=detail)

    xlsx_path = svc.data_dir / Path(batch.merged_xlsx_path)
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="merged XLSX file missing")

    # Filename: follow the same naming policy as per-item download
    debtor_inn: str | None = None
    calc_date: str | None = None
    if batch.items:
        debtor_inn = str(batch.items[0].debtor.inn or "") or None
        calc_date = str(batch.items[0].params.calc_date or "") or None

    try:
        from app.api.items import _build_download_filename  # type: ignore

        out_name = _build_download_filename(
            debtor_inn=debtor_inn,
            calc_date=calc_date,
        )
    except Exception:
        out_name = "merged.xlsx"

    return FileResponse(
        path=str(xlsx_path),
        filename=out_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{batch_id}/download/pdf")
async def download_batch_pdf(batch_id: str) -> Any:
    """Download merged PDF (converted from merged XLSX), if present."""
    svc = ProcessingService()
    bp = _paths(svc, batch_id)
    if not bp.batch_json.exists():
        raise HTTPException(status_code=404, detail="batch not found")

    batch = _load_batch(bp.batch_json)
    if batch.merge_status != "MERGED" or not batch.merged_xlsx_path:
        detail = batch.merge_warning or "merged XLSX not available"
        raise HTTPException(status_code=404, detail=detail)

    xlsx_path = svc.data_dir / Path(batch.merged_xlsx_path)
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="merged XLSX file missing")

    try:
        pdf_path = convert_xlsx_to_pdf(xlsx_path)
    except PdfConversionError as e:
        msg = str(e)
        if "not installed" in msg.lower() or "soffice" in msg.lower():
            raise HTTPException(status_code=501, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    # Filename: same policy as XLSX, only different extension
    debtor_inn: str | None = None
    calc_date: str | None = None
    if batch.items:
        debtor_inn = str(batch.items[0].debtor.inn or "") or None
        calc_date = str(batch.items[0].params.calc_date or "") or None

    try:
        from app.api.items import _build_download_filename, _with_pdf_ext  # type: ignore

        out_name = _with_pdf_ext(
            _build_download_filename(debtor_inn=debtor_inn, calc_date=calc_date)
        )
    except Exception:
        out_name = "merged.pdf"

    return FileResponse(
        path=str(pdf_path),
        filename=out_name,
        media_type="application/pdf",
    )
