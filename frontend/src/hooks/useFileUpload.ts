// frontend/src/hooks/useFileUpload.ts

import { useCallback, useMemo, useRef, useState } from "react";
import type {
  ClientFileId,
  ConsumerCategory,
  DDMMYYYY,
  DebtorPreview,
  InspectResponse,
  ProcessItemMeta,
} from "../types";
import { pdfService } from "../services/pdfService";
import { batchService } from "../services/batchService";
import { ApiError } from "../api/client";

export type UploadPhase =
  | "idle"
  | "inspecting"
  | "ready"
  | "processing"
  | "error";

export interface DraftItem {
  clientFileId: ClientFileId;
  file: File; // IMPORTANT: stable in-memory copy

  debtor: DebtorPreview; // filled after inspect (can still be nulls)

  // NEW (non-breaking): from /api/pdfs/inspect (scan/no text layer)
  needs_ocr?: boolean;
  inspect_warning?: string | null;

  params: {
    category: ConsumerCategory;
    rate_percent: number;
    overdue_day: number; // 1..31
    calc_date: DDMMYYYY;
    exclude_zero_debt_periods: boolean;
    add_state_duty: boolean;
  };

  inspectWarnings: string[];
  inspectError?: string;

  validationErrors: Record<string, string>;
}

export interface UseFileUploadState {
  phase: UploadPhase;
  items: DraftItem[];
  globalError?: string;

  innMismatch: {
    hasMismatch: boolean;
    inns: string[]; // unique non-empty inns
  };

  canProcess: boolean;

  // NEW: UI checkbox (default true)
  mergeXlsx: boolean;
}

export interface UseFileUploadActions {
  addFiles: (files: File[]) => void;
  removeItem: (clientFileId: ClientFileId) => void;
  clearAll: () => void;

  updateItemParams: (
    clientFileId: ClientFileId,
    patch: Partial<DraftItem["params"]>,
  ) => void;

  // Row actions for icons
  copyDown: (clientFileId: ClientFileId) => void;
  copyToAll: (clientFileId: ClientFileId) => void;
  moveUp: (clientFileId: ClientFileId) => void;
  moveDown: (clientFileId: ClientFileId) => void;
  resetParams: (clientFileId: ClientFileId) => void;

  runInspect: () => Promise<void>;
  processBatch: () => Promise<{ batchId: string }>;

  // NEW: setter for merge checkbox
  setMergeXlsx: (value: boolean) => void;
}

export function useFileUpload(): {
  state: UseFileUploadState;
  actions: UseFileUploadActions;
} {
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [globalError, setGlobalError] = useState<string | undefined>(undefined);

  // checkbox state (default checked)
  const [mergeXlsx, setMergeXlsx] = useState<boolean>(true);

  // Prevent stale inspect results from overwriting newer state
  const inspectRunIdRef = useRef<number>(0);

  const innMismatch = useMemo(() => {
    const inns = uniqueNonEmpty(
      items.map((it) => it.debtor.inn ?? "").map(normalizeInn),
    );
    return { hasMismatch: inns.length > 1, inns };
  }, [items]);

  const canProcess = useMemo(() => {
    if (items.length === 0) return false;
    if (phase === "inspecting" || phase === "processing") return false;

    return items.every((it) => Object.keys(it.validationErrors).length === 0);
  }, [items, phase]);

  /**
   * Critical: stabilize selected files immediately.
   * This prevents Chrome/Chromium net::ERR_UPLOAD_FILE_CHANGED on later upload
   * (inspect/process) when input is cleared, HMR runs, etc.
   */
  const addFiles = useCallback((files: File[]) => {
    const pdfs = files.filter(isPdfFile);
    if (pdfs.length === 0) return;

    setGlobalError(undefined);

    void (async () => {
      try {
        const stable = await Promise.all(pdfs.map(stabilizeFile));

        setItems((prev) => {
          const next: DraftItem[] = [...prev];

          for (const file of stable) {
            const clientFileId = createClientFileId();
            const draft: DraftItem = {
              clientFileId,
              file,
              debtor: { name: null, inn: null },
              needs_ocr: false,
              inspect_warning: null,
              params: {
                category: "Прочие",
                rate_percent: 9,
                overdue_day: 1,
                calc_date: todayDDMMYYYY(),
                exclude_zero_debt_periods: false,
                add_state_duty: false,
              },
              inspectWarnings: [],
              validationErrors: {},
            };
            draft.validationErrors = validateDraftItem(draft);
            next.push(draft);
          }
          return next;
        });

        setPhase((p) => (p === "idle" ? "ready" : p));
      } catch (e) {
        const msg = formatError(e);
        setGlobalError(msg);
        setPhase("error");
      }
    })();
  }, []);

  const removeItem = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) => {
      const next = prev.filter((it) => it.clientFileId !== clientFileId);
      if (next.length === 0) setPhase("idle");
      return next;
    });
    setGlobalError(undefined);
  }, []);

  const clearAll = useCallback(() => {
    setItems([]);
    setGlobalError(undefined);
    setPhase("idle");
  }, []);

  const updateItemParams = useCallback(
    (clientFileId: ClientFileId, patch: Partial<DraftItem["params"]>) => {
      setItems((prev) =>
        prev.map((it) => {
          if (it.clientFileId !== clientFileId) return it;
          const next: DraftItem = {
            ...it,
            params: { ...it.params, ...patch },
            validationErrors: it.validationErrors,
          };
          next.validationErrors = validateDraftItem(next);
          return next;
        }),
      );
    },
    [],
  );

  // ===== Row actions (for icons) =====

  const copyDown = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) => {
      const idx = prev.findIndex((x) => x.clientFileId === clientFileId);
      if (idx < 0 || idx >= prev.length - 1) return prev;

      const src = prev[idx];
      const dst = prev[idx + 1];

      const updatedDst: DraftItem = {
        ...dst,
        params: { ...src.params },
        validationErrors: dst.validationErrors,
      };
      updatedDst.validationErrors = validateDraftItem(updatedDst);

      const next = [...prev];
      next[idx + 1] = updatedDst;
      return next;
    });
  }, []);

  const copyToAll = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) => {
      const src = prev.find((x) => x.clientFileId === clientFileId);
      if (!src) return prev;

      return prev.map((it) => {
        if (it.clientFileId === clientFileId) return it;
        const next: DraftItem = {
          ...it,
          params: { ...src.params },
          validationErrors: it.validationErrors,
        };
        next.validationErrors = validateDraftItem(next);
        return next;
      });
    });
  }, []);

  const moveUp = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) => {
      const idx = prev.findIndex((x) => x.clientFileId === clientFileId);
      if (idx <= 0) return prev;
      const next = [...prev];
      const tmp = next[idx - 1];
      next[idx - 1] = next[idx];
      next[idx] = tmp;
      return next;
    });
  }, []);

  const moveDown = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) => {
      const idx = prev.findIndex((x) => x.clientFileId === clientFileId);
      if (idx < 0 || idx >= prev.length - 1) return prev;
      const next = [...prev];
      const tmp = next[idx + 1];
      next[idx + 1] = next[idx];
      next[idx] = tmp;
      return next;
    });
  }, []);

  const resetParams = useCallback((clientFileId: ClientFileId) => {
    setItems((prev) =>
      prev.map((it) => {
        if (it.clientFileId !== clientFileId) return it;

        const next: DraftItem = {
          ...it,
          params: {
            category: "Прочие",
            rate_percent: 9,
            overdue_day: 1,
            calc_date: "01.01.2025" as DDMMYYYY,
            exclude_zero_debt_periods: false,
            add_state_duty: false,
          },
          validationErrors: it.validationErrors,
        };
        next.validationErrors = validateDraftItem(next);
        return next;
      }),
    );
  }, []);

  // ===== Inspect / Process =====

  const runInspect = useCallback(async () => {
    if (items.length === 0) return;

    setGlobalError(undefined);
    setPhase("inspecting");

    const runId = ++inspectRunIdRef.current;
    const filesSnapshot = items.map((it) => it.file);

    try {
      const res = await pdfService.inspect(filesSnapshot);

      if (inspectRunIdRef.current !== runId) return;

      // IMPORTANT: merge into existing list (do not replace)
      setItems((prev) => applyInspectResponse(prev, res));
      setPhase("ready");
    } catch (e) {
      if (inspectRunIdRef.current !== runId) return;

      const msg = formatError(e);
      setGlobalError(msg);
      setPhase("error");
    }
  }, [items]);

  const processBatch = useCallback(async (): Promise<{ batchId: string }> => {
    if (items.length === 0) {
      throw new Error("No items to process");
    }

    setGlobalError(undefined);
    setPhase("processing");

    // If an inspect is in-flight, invalidate it (so it can't overwrite)
    inspectRunIdRef.current += 1;

    const filesSnapshot = items.map((it) => it.file);
    const metaSnapshot: ProcessItemMeta[] = items.map((it) => ({
      client_file_id: it.clientFileId,
      file_name: it.file.name,

      calc_date: it.params.calc_date,
      category: it.params.category,

      rate_percent: it.params.rate_percent,
      overdue_day: it.params.overdue_day,
      exclude_zero_debt_periods: it.params.exclude_zero_debt_periods,
      add_state_duty: it.params.add_state_duty,
    }));

    try {
      // IMPORTANT: pass merge flag to backend
      const resp = await batchService.process(filesSnapshot, metaSnapshot, {
        merge_xlsx: mergeXlsx,
      });
      setPhase("ready");
      return { batchId: resp.batch_id };
    } catch (e) {
      const msg = formatError(e);
      setGlobalError(msg);
      setPhase("error");
      throw e;
    }
  }, [items, mergeXlsx]); // ✅ include mergeXlsx

  const state: UseFileUploadState = {
    phase,
    items,
    globalError,
    innMismatch,
    canProcess,
    mergeXlsx, // ✅ include in returned state
  };

  const actions: UseFileUploadActions = {
    addFiles,
    removeItem,
    clearAll,
    updateItemParams,

    copyDown,
    copyToAll,
    moveUp,
    moveDown,
    resetParams,

    runInspect,
    processBatch,

    setMergeXlsx, // ✅ include in returned actions
  };

  // ✅ FIX: return full state/actions (not only mergeXlsx)
  return { state, actions };
}

/* ===========================
   Helpers
=========================== */

function isPdfFile(f: File): boolean {
  if (f.type === "application/pdf") return true;
  return f.name.toLowerCase().endsWith(".pdf");
}

/**
 * Create a stable in-memory copy of the file.
 * This avoids net::ERR_UPLOAD_FILE_CHANGED on Chromium in some UI flows.
 */
async function stabilizeFile(src: File): Promise<File> {
  const bytes = await src.arrayBuffer();
  return new File([bytes], src.name, {
    type: src.type || "application/pdf",
    lastModified: src.lastModified,
  });
}

function createClientFileId(): ClientFileId {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID() as string as ClientFileId;
  }
  return `cf_${Date.now()}_${Math.random().toString(16).slice(2)}` as string as ClientFileId;
}

function validateDraftItem(it: DraftItem): Record<string, string> {
  const errs: Record<string, string> = {};

  if (!it.params.category) errs["category"] = "Категория обязательна";

  if (!Number.isFinite(it.params.rate_percent))
    errs["rate_percent"] = "Учетная ставка должна быть числом";
  if (it.params.rate_percent < 0)
    errs["rate_percent"] = "Учетная ставка не может быть отрицательной";

  if (!Number.isFinite(it.params.overdue_day))
    errs["overdue_day"] = "День начала просрочки должен быть числом";
  if (
    Number.isFinite(it.params.overdue_day) &&
    (!Number.isInteger(it.params.overdue_day) ||
      it.params.overdue_day < 1 ||
      it.params.overdue_day > 31)
  ) {
    errs["overdue_day"] = "День начала просрочки: целое число от 1 до 31";
  }

  if (!isDDMMYYYY(it.params.calc_date))
    errs["calc_date"] = "Дата расчета: формат ДД.ММ.ГГГГ";

  return errs;
}

function isDDMMYYYY(v: string): v is DDMMYYYY {
  return /^\d{2}\.\d{2}\.\d{4}$/.test(v);
}

function applyInspectResponse(
  prev: DraftItem[],
  res: InspectResponse,
): DraftItem[] {
  const prevByName: Map<string, DraftItem[]> = new Map();
  for (const it of prev) {
    const key = it.file.name;
    const arr = prevByName.get(key) ?? [];
    arr.push(it);
    prevByName.set(key, arr);
  }

  const used = new Set<ClientFileId>();
  const next = prev.map((it) => ({ ...it }));

  for (const r of res.items) {
    const candidates = prevByName.get(r.filename) ?? [];
    const pick = candidates.find((c) => !used.has(c.clientFileId));
    if (!pick) continue;

    used.add(pick.clientFileId);
    const idx = next.findIndex((x) => x.clientFileId === pick.clientFileId);
    if (idx < 0) continue;

    const anyR = r as any;
    const needsOcr = Boolean(anyR.needs_ocr);
    const ocrWarn = (anyR.inspect_warning ?? null) as string | null;

    const updated: DraftItem = {
      ...next[idx],
      debtor: {
        name: r.debtor.name ?? null,
        inn: r.debtor.inn ?? null,
      },
      needs_ocr: needsOcr,
      inspect_warning: ocrWarn,
      inspectWarnings: r.warnings ?? [],
      validationErrors: next[idx].validationErrors,
    };
    updated.validationErrors = validateDraftItem(updated);
    next[idx] = updated;
  }

  return next;
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) return e.message || `HTTP ${e.status}`;
  if (e instanceof Error) return e.message;
  return "Неизвестная ошибка";
}

function normalizeInn(v: string): string {
  return v.replace(/\s+/g, "");
}

function uniqueNonEmpty(arr: string[]): string[] {
  const set = new Set<string>();
  for (const x of arr) {
    const v = x.trim();
    if (!v) continue;
    set.add(v);
  }
  return Array.from(set);
}

function todayDDMMYYYY(): DDMMYYYY {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = String(d.getFullYear());
  return `${dd}.${mm}.${yyyy}` as DDMMYYYY;
}
