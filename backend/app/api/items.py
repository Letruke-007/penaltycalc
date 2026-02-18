from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.processing_service import ProcessingService

from app.utils.xlsx_to_pdf import PdfConversionError, convert_xlsx_to_pdf

router = APIRouter(prefix="/items", tags=["items"])


def _with_xlsx_ext(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return name[:-4] + ".xlsx"
    if lower.endswith(".xlsx"):
        return name
    return name + ".xlsx"


def _with_pdf_ext(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".xlsx"):
        return name[:-5] + ".pdf"
    if lower.endswith(".pdf"):
        return name
    return name + ".pdf"


# Candidate mapping (filtered by opf.yml presence at runtime)
_OPF_CANDIDATES_FULL_TO_SHORT: Dict[str, str] = {
    "Общество с ограниченной ответственностью": "ООО",
    "Акционерное общество": "АО",
    "Публичное акционерное общество": "ПАО",
    "Непубличное акционерное общество": "АО",
    "Товарищество собственников жилья": "ТСЖ",
    "Жилищно-строительный кооператив": "ЖСК",
    "Жилищный кооператив": "ЖК",
    "Государственное унитарное предприятие": "ГУП",
    "Муниципальное унитарное предприятие": "МУП",
    "Государственное бюджетное учреждение": "ГБУ",
    "Государственное автономное учреждение": "ГАУ",
    "Государственное казенное учреждение": "ГКУ",
    "Муниципальное бюджетное учреждение": "МБУ",
    "Муниципальное казенное учреждение": "МКУ",
    "Федеральное казенное учреждение": "ФКУ",
    "Федеральное государственное бюджетное учреждение": "ФГБУ",
    "Федеральное государственное автономное учреждение": "ФГАУ",
    "Федеральное государственное казенное учреждение": "ФГКУ",
    "Автономная некоммерческая организация": "АНО",
    "Некоммерческая организация": "НКО",
}


@lru_cache(maxsize=1)
def _load_opf_items() -> set[str]:
    """
    Read backend/app/data/opf.yml as a simple YAML list:
      version: "1.0"
      items:
      - ...
    We avoid PyYAML dependency and parse only "- <text>" lines.
    """
    # items.py is in backend/app/api/items.py -> parents[1] == backend/app
    opf_path = Path(__file__).resolve().parents[1] / "data" / "opf.yml"
    if not opf_path.exists():
        return set()

    items: list[str] = []
    for raw in opf_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            items.append(line[2:].strip())
    return set(items)


@lru_cache(maxsize=1)
def _opf_full_to_short_map() -> Dict[str, str]:
    """
    Build mapping full->short but only keep pairs where both entries
    exist in opf.yml (so opf.yml remains the source of truth).
    """
    opf_items = _load_opf_items()
    out: Dict[str, str] = {}
    for full, short in _OPF_CANDIDATES_FULL_TO_SHORT.items():
        if full in opf_items and short in opf_items:
            out[full] = short
    return out


def _shorten_opf_for_filename(name: str) -> str:
    """
    Replace FULL OPF at the start of debtor name with SHORT OPF,
    only for filename generation.
    """
    s = (name or "").strip()
    if not s:
        return s

    mapping = _opf_full_to_short_map()
    low = s.lower()

    for full, short in mapping.items():
        if low.startswith(full.lower()):
            rest = s[len(full) :].lstrip(" ,")
            return (short + " " + rest).strip()

    return s


def _sanitize_filename_component(s: str) -> str:
    """
    Make a Windows-safe filename part:
      - shorten OPF (full -> short) using opf.yml-filtered mapping
      - remove quotes entirely
      - remove forbidden filesystem characters
      - normalize whitespace
    """
    s = _shorten_opf_for_filename((s or "").strip())
    if not s:
        return ""

    # Remove any quotes entirely
    s = s.replace('"', "").replace("«", "").replace("»", "")

    # Remove filesystem-forbidden characters on Windows
    for bad in ["\\", "/", ":", "*", "?", "<", ">", "|"]:
        s = s.replace(bad, " ")

    s = " ".join(s.split())
    return s


def _build_download_filename(
    *,
    debtor_name: str,
    contract_number: str,
    calc_date: str | None,
) -> str:
    debtor_name = _sanitize_filename_component(debtor_name)
    contract_number = (contract_number or "").strip()

    multi = False
    cn_low = contract_number.lower()
    if "несколь" in cn_low:
        multi = True
    if any(sep in contract_number for sep in [",", ";", "\n"]):
        multi = True

    if multi:
        contract_part = "несколько договоров"
    else:
        contract_part = f"договор № {contract_number or '___________'}"

    date_part = f" на {calc_date}" if calc_date else ""

    base = (
        f"Расчет долга и пени по должнику "
        f"{debtor_name or '___________'} "
        f"{contract_part}"
        f"{date_part}"
    ).strip()

    return _with_xlsx_ext(base)


@router.get("/{item_id}/download/xlsx")
async def download_item_xlsx(item_id: str) -> Any:
    """
    item_id format: "{batch_id}:{file_name}"
    """
    if ":" not in item_id:
        raise HTTPException(status_code=422, detail="invalid item_id format")

    batch_id, _file_name = item_id.split(":", 1)

    svc = ProcessingService()
    batch_dir = svc.data_dir / "batches" / batch_id
    batch_json = batch_dir / "batch.json"
    if not batch_json.exists():
        raise HTTPException(status_code=404, detail="batch not found")

    batch = json.loads(batch_json.read_text(encoding="utf-8"))
    items = batch.get("items", [])
    target: dict[str, Any] | None = None
    for it in items:
        if it.get("item_id") == item_id:
            target = it
            break
    if not target:
        raise HTTPException(status_code=404, detail="item not found")

    xlsx_rel = target.get("xlsx_path")
    if not xlsx_rel:
        raise HTTPException(status_code=404, detail="xlsx not ready")

    xlsx_path = svc.data_dir / Path(str(xlsx_rel))
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="xlsx file missing")

    # Prefer naming from produced JSON (source of truth), fallback to inspect preview.
    debtor_name = ""
    contract_number = ""
    calc_date = None

    json_rel = target.get("json_path")
    if json_rel:
        json_path = svc.data_dir / Path(str(json_rel))
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                st = payload.get("statement") or {}
                debtor = st.get("debtor") or {}
                contract = st.get("contract") or {}

                debtor_name = str(debtor.get("name") or "")
                contract_number = str(contract.get("number") or "")
                calc_date = str(st.get("calc_date") or "")
            except Exception:
                debtor_name = ""
                contract_number = ""
                calc_date = None

    if not debtor_name:
        debtor = target.get("debtor") or {}
        debtor_name = str(debtor.get("name") or "")

    out_name = _build_download_filename(
        debtor_name=debtor_name,
        contract_number=contract_number,
        calc_date=calc_date,
    )

    return FileResponse(
        path=str(xlsx_path),
        filename=out_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{item_id}/download/pdf")
async def download_item_pdf(item_id: str) -> Any:
    """
    item_id format: "{batch_id}:{file_name}"
    Returns PDF converted from generated XLSX (cached next to XLSX).
    """
    if ":" not in item_id:
        raise HTTPException(status_code=422, detail="invalid item_id format")

    batch_id, _file_name = item_id.split(":", 1)

    svc = ProcessingService()
    batch_dir = svc.data_dir / "batches" / batch_id
    batch_json = batch_dir / "batch.json"
    if not batch_json.exists():
        raise HTTPException(status_code=404, detail="batch not found")

    batch = json.loads(batch_json.read_text(encoding="utf-8"))
    items = batch.get("items", [])
    target: dict[str, Any] | None = None
    for it in items:
        if it.get("item_id") == item_id:
            target = it
            break
    if not target:
        raise HTTPException(status_code=404, detail="item not found")

    xlsx_rel = target.get("xlsx_path")
    if not xlsx_rel:
        raise HTTPException(status_code=404, detail="xlsx not ready")

    xlsx_path = svc.data_dir / Path(str(xlsx_rel))
    if not xlsx_path.exists():
        raise HTTPException(status_code=404, detail="xlsx file missing")

    # Prefer naming from produced JSON (source of truth), fallback to inspect preview.
    debtor_name = ""
    contract_number = ""
    calc_date: str | None = None

    json_rel = target.get("json_path")
    if json_rel:
        json_path = svc.data_dir / Path(str(json_rel))
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                st = payload.get("statement") or {}
                debtor = st.get("debtor") or {}
                contract = st.get("contract") or {}

                debtor_name = str(debtor.get("name") or "")
                contract_number = str(contract.get("number") or "")
                calc_date = str(st.get("calc_date") or "") or None
            except Exception:
                debtor_name = ""
                contract_number = ""
                calc_date = None

    if not debtor_name:
        debtor = target.get("debtor") or {}
        debtor_name = str(debtor.get("name") or "")

    base_name_xlsx = _build_download_filename(
        debtor_name=debtor_name,
        contract_number=contract_number,
        calc_date=calc_date,
    )
    out_name_pdf = _with_pdf_ext(base_name_xlsx)

    try:
        pdf_path = convert_xlsx_to_pdf(xlsx_path)
    except PdfConversionError as e:
        msg = str(e)
        if "not installed" in msg.lower() or "soffice" in msg.lower():
            raise HTTPException(status_code=501, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    return FileResponse(
        path=str(pdf_path),
        filename=out_name_pdf,
        media_type="application/pdf",
    )
