// frontend/src/services/batchService.ts

import type { Batch, CreateBatchProcessResponse, ProcessItemMeta } from "../types";
import { api } from "./api";

export const batchService = {
  async process(
    files: File[],
    itemsMeta: ProcessItemMeta[],
    opts?: { merge_xlsx?: boolean },
  ): Promise<CreateBatchProcessResponse> {
    const form = new FormData();

    for (const f of files) form.append("files", f, f.name);
    form.append("items_meta", JSON.stringify(itemsMeta));
    form.append("merge_xlsx", String(opts?.merge_xlsx ?? true));

    return api.postForm<CreateBatchProcessResponse>("/api/batches/process", form);
  },

  async get(batchId: string): Promise<Batch> {
    return api.getJson<Batch>(`/api/batches/${encodeURIComponent(batchId)}`);
  },

  async downloadBatchXlsx(batchId: string): Promise<void> {
    const path = `/api/batches/${encodeURIComponent(batchId)}/download/xlsx`;
    const res = await api.getRaw(path);
    const blob = await res.blob();

    const cd = res.headers.get("content-disposition") ?? "";
    const filename = parseFilenameFromContentDisposition(cd) ?? "merged.xlsx";
    triggerBrowserDownload(blob, filename);
  },

  async downloadBatchPdf(batchId: string): Promise<void> {
    const path = `/api/batches/${encodeURIComponent(batchId)}/download/pdf`;
    const res = await api.getRaw(path);
    const blob = await res.blob();

    const cd = res.headers.get("content-disposition") ?? "";
    const filename = parseFilenameFromContentDisposition(cd) ?? "merged.pdf";
    triggerBrowserDownload(blob, filename);
  },

  /**
   * Per item download:
   * GET /api/items/{item_id}/download/xlsx
   *
   * Fetch as Blob BUT use filename from Content-Disposition.
   * This keeps SPA on the same page and respects backend naming.
   */
  async downloadItemXlsx(itemId: string): Promise<void> {
    const path = `/api/items/${encodeURIComponent(itemId)}/download/xlsx`;

    const res = await api.getRaw(path);
    const blob = await res.blob();

    const cd = res.headers.get("content-disposition") ?? "";
    const filename = parseFilenameFromContentDisposition(cd) ?? fallbackXlsxName(itemId);

    triggerBrowserDownload(blob, filename);
  },

  async downloadItemPdf(itemId: string): Promise<void> {
    const path = `/api/items/${encodeURIComponent(itemId)}/download/pdf`;

    const res = await api.getRaw(path);
    const blob = await res.blob();

    const cd = res.headers.get("content-disposition") ?? "";
    const filename = parseFilenameFromContentDisposition(cd) ?? fallbackPdfName(itemId);

    triggerBrowserDownload(blob, filename);
  },
};

function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function parseFilenameFromContentDisposition(cd: string): string | null {
  // RFC 5987: filename*=UTF-8''...
  const m5987 = cd.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (m5987?.[1]) {
    try {
      return decodeURIComponent(m5987[1].trim());
    } catch {
      // ignore
    }
  }

  // Basic: filename="..."
  const mQuoted = cd.match(/filename\s*=\s*"([^"]+)"/i);
  if (mQuoted?.[1]) return mQuoted[1].trim();

  // Basic: filename=...
  const mPlain = cd.match(/filename\s*=\s*([^;]+)/i);
  if (mPlain?.[1]) return mPlain[1].trim();

  return null;
}

function fallbackXlsxName(itemId: string): string {
  // itemId format: "{batch_id}:{file_name}"
  const parts = itemId.split(":");
  const file = parts.length > 1 ? parts.slice(1).join(":") : "result.pdf";
  return file.toLowerCase().endsWith(".pdf") ? file.slice(0, -4) + ".xlsx" : file + ".xlsx";
}

function fallbackPdfName(itemId: string): string {
  // itemId format: "{batch_id}:{file_name}"
  const parts = itemId.split(":");
  const file = parts.length > 1 ? parts.slice(1).join(":") : "result.xlsx";
  const low = file.toLowerCase();
  if (low.endsWith(".xlsx")) return file.slice(0, -5) + ".pdf";
  if (low.endsWith(".pdf")) return file;
  return file + ".pdf";
}