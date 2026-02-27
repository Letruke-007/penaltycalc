// frontend/src/types/pdf.ts

export type DDMMYYYY = string;
export type ClientFileId = string;
export type BatchId = string;

export type ConsumerCategory =
  | "Прочие"
  | "ТСЖ, ЖСК, ЖК"
  | "УК"
  | "Собственники жилых помещений в МКД"
  | "Собственники нежилых помещений в МКД";

export interface DebtorPreview {
  name: string | null;
  inn: string | null;
}

export interface ItemCalcParams {
  calc_date: DDMMYYYY;
  category: ConsumerCategory;

  rate_percent: number;
  overdue_day: number; // 1..31
  exclude_zero_debt_periods: boolean;
  add_state_duty: boolean;
}

export interface ProcessItemMeta {
  client_file_id: ClientFileId;
  file_name: string;

  calc_date: DDMMYYYY;
  category: ConsumerCategory;

  rate_percent: number;
  overdue_day: number;
  exclude_zero_debt_periods: boolean;
  add_state_duty: boolean;
}

export interface CreateBatchProcessResponse {
  batch_id: BatchId;
}

export type BatchItemStatus =
  | "PENDING"
  | "INSPECTED"
  | "PROCESSING"
  | "DONE"
  | "ERROR";
export type BatchStatus = "RUNNING" | "DONE" | "ERROR";

export interface BatchItem {
  item_id: string;
  client_file_id: ClientFileId;
  file_name: string;

  status: BatchItemStatus;
  error?: string;

  debtor: DebtorPreview;
  params: ItemCalcParams;

  json_path?: string;
  xlsx_path?: string;
}

export interface Batch {
  batch_id: BatchId;
  status: BatchStatus;
  created_at: string;

  total_items: number;
  done_items: number;
  error_items: number;

  items: BatchItem[];
  error?: string;

  merge_enabled?: boolean;
  merge_status?: "MERGED" | "SKIPPED" | "ERROR" | null;
  merge_warning?: string | null;
  merge_error?: string | null;
  merged_xlsx_path?: string | null;
}

export interface InspectItemResult {
  filename: string;
  debtor: DebtorPreview;
  warnings: string[];
  error?: string | null;
}

export interface InspectResponse {
  items: InspectItemResult[];
}
