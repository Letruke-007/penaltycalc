// frontend/src/types/batch.ts

import type { ClientFileId, DebtorPreview, ItemCalcParams } from "./pdf";

export type BatchId = string;

export type BatchState =
  | "queued"
  | "inspecting"
  | "processing"
  | "completed"
  | "completed_with_errors"
  | "failed";

export type BatchItemState = "queued" | "inspecting" | "processing" | "done" | "error";

export interface BatchItemError {
  code: string;
  message: string;
  details?: string;
}

export interface BatchItemResultLinks {
  xlsx?: string; // URL to download generated XLSX for this item
  pdf?: string; // optional: URL to download stored/normalized PDF if backend provides it
}

export interface BatchItem {
  id: string;
  item_id?: string;

  client_file_id?: ClientFileId; // optional if backend doesn't preserve it
  filename: string;

  state: BatchItemState;

  debtor?: DebtorPreview; // becomes available after inspect phase

  // Non-fatal warnings produced during processing (PDF→JSON and/or JSON→XLSX)
  warnings?: string[];

  // In status mode params may be missing (e.g., not preserved by backend or not rehydrated)
  params?: ItemCalcParams;

  // Back-compat field used by UI (if backend provides direct url)
  xlsx_url?: string;

  result?: BatchItemResultLinks;
  error?: BatchItemError;
}

export interface Batch {
  id: BatchId;
  created_at?: string; // ISO string, optional
  state: BatchState;

  total_items: number;
  done_items: number;
  error_items: number;

  items: BatchItem[];
}

export interface CreateBatchProcessResponse {
  batch_id: BatchId;
}
