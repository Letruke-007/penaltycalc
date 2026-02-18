// frontend/src/pages/BatchStatus.tsx

import React, { useCallback, useMemo } from "react";
import { RefreshCcw } from "lucide-react";
import { ItemsTable } from "../components/ItemsTable";
import type { BatchId } from "../types";
import { useBatchStatus } from "../hooks/useBatchStatus";
import { batchService } from "../services/batchService";

export interface BatchStatusProps {
  batchId: BatchId;
}

export function BatchStatus(props: BatchStatusProps) {
  const { batchId } = props;
  const { state, actions } = useBatchStatus(batchId);

  const onDownloadItemXlsx = useCallback(async (itemId: string, _filename?: string) => {
    await batchService.downloadItemXlsx(itemId);
  }, []);

  const onDownloadItemPdf = useCallback(async (itemId: string, _filename?: string) => {
    await batchService.downloadItemPdf(itemId);
  }, []);

  const onDownloadMerged = useCallback(async () => {
    await batchService.downloadBatchXlsx(batchId);
  }, [batchId]);

  const onDownloadMergedPdf = useCallback(async () => {
    await batchService.downloadBatchPdf(batchId);
  }, [batchId]);

  const b: any = state.batch;

  const canDownloadMerged = Boolean(b && b.merge_status === "MERGED");
  const showMergeWarning = Boolean(b && b.merge_status === "SKIPPED" && b.merge_warning);
  const showMergeError = Boolean(b && b.merge_status === "ERROR" && b.merge_error);

  // StatusBadge expects "phase"-like; we map batch status to the same vocabulary
  const phase = useMemo(() => {
    if (!b) return "idle";
    switch (String(b.status)) {
      case "RUNNING":
        return "processing";
      case "DONE":
        return "ready";
      case "ERROR":
        return "error";
      default:
        return "idle";
    }
  }, [b]);

  return (
    <div style={{ minWidth: 0 }}>
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Статус обработки</div>
          <div style={{ fontSize: 13, color: "#525252", lineHeight: 1.35 }}>
            Здесь отображаются результаты последней обработки (или выбранной из истории слева).
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            onClick={() => void actions.reload()}
            title="Обновить"
            style={iconBtnStyle(false)}
          >
            <RefreshCcw size={18} />
          </button>

          <button
            type="button"
            onClick={() => void onDownloadMerged()}
            disabled={!canDownloadMerged}
            style={btnPrimaryStyle(!canDownloadMerged)}
            title={
              canDownloadMerged
                ? "Скачать объединённый XLSX"
                : "Объединённый XLSX недоступен (объединение не выполнено или отключено)"
            }
          >
            Скачать объединённый XLSX
          </button>

          <button
            type="button"
            onClick={() => void onDownloadMergedPdf()}
            disabled={!canDownloadMerged}
            style={btnSecondaryStyle(!canDownloadMerged)}
            title={
              canDownloadMerged
                ? "Скачать PDF (из объединённого XLSX)"
                : "PDF недоступен, пока не сформирован объединённый XLSX"
            }
          >
            Скачать PDF
          </button>
        </div>
      </div>

      {state.error && (
        <div style={bannerErrorStyle}>
          <span style={{ fontWeight: 700 }}>Ошибка получения статуса.</span>&nbsp;
          <span style={{ whiteSpace: "pre-wrap" }}>{state.error}</span>
        </div>
      )}

      {b && (
        <>
          {/* Command bar (same framing as UploadBatch) */}
          <div style={commandBarWrapStyle}>
            <div style={{ ...commandBarStyle, gridTemplateColumns: "minmax(0,1fr)" }}>
              <div style={leftGroupStyle}>
                <div style={kvRowStyle}>
                  <KV k="Состояние" v={humanBatchStatus(b.status)} />
                  <KV k="Готово" v={`${state.progress.done} / ${state.progress.total}`} />
                  <KV k="Ошибок" v={`${state.progress.errors}`} />
                  <KV k="Создан" v={new Date(b.created_at).toLocaleString()} />
                  {typeof b.merge_enabled === "boolean" && <KV k="Объединение" v={b.merge_enabled ? "Да" : "Нет"} />}
                </div>
              </div>
            </div>

            {showMergeWarning && (
              <div style={bannerWarnStyle}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>Объединение не выполнено</div>
                <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{String(b.merge_warning)}</div>
                <div style={{ fontSize: 13, marginTop: 8, color: "#525252" }}>
                  В этом режиме файл формируется отдельно по каждой справке.
                </div>
              </div>
            )}

            {showMergeError && (
              <div style={bannerErrorStyle}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>Ошибка объединения</div>
                <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{String(b.merge_error)}</div>
              </div>
            )}
          </div>

          {/* Section header (same as UploadBatch) */}
          <div style={sectionHeadStyle}>
            <div style={sectionTitleStyle}>Результаты</div>

            <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
              <div style={sectionMetaStyle}>Всего: {Array.isArray(b.items) ? b.items.length : 0}</div>
              <StatusBadge phase={phase} />
            </div>
          </div>

          <div style={tableCardStyle}>
            <ItemsTable
              mode="status"
              items={b.items}
              onDownloadItemXlsx={onDownloadItemXlsx}
              onDownloadItemPdf={onDownloadItemPdf}
            />
          </div>
        </>
      )}

      {!b && !state.error && <div style={{ fontSize: 13, color: "#525252" }}>Загрузка статуса…</div>}
    </div>
  );
}

/* ======================
   KV
====================== */

function KV(props: { k: string; v: string }) {
  return (
    <div style={{ minWidth: 160 }}>
      <div style={{ fontSize: 12, color: "#525252", marginBottom: 4 }}>{props.k}</div>
      <div style={{ fontSize: 14, fontWeight: 700 }}>{props.v}</div>
    </div>
  );
}

function humanBatchStatus(s: string): string {
  switch (s) {
    case "RUNNING":
      return "В работе";
    case "DONE":
      return "Готово";
    case "ERROR":
      return "Ошибка";
    default:
      return s;
  }
}

/* ======================
   Status badge (copied exactly from UploadBatch styles)
====================== */

function StatusBadge(props: { phase: string }) {
  const { phase } = props;

  const { text, style } = useMemo(() => {
    switch (phase) {
      case "ready":
        return { text: "Готово", style: statusBadgeSuccessStyle };
      case "inspecting":
        return { text: "Извлечение", style: statusBadgeInfoStyle };
      case "processing":
        return { text: "Обработка", style: statusBadgeInfoStyle };
      case "error":
        return { text: "Ошибка", style: statusBadgeDangerStyle };
      case "idle":
        return { text: "Ожидание", style: statusBadgeNeutralStyle };
      default:
        return { text: phase, style: statusBadgeNeutralStyle };
    }
  }, [phase]);

  return <div style={style}>{text}</div>;
}

/* ======================
   Styles (taken 1:1 from UploadBatch.tsx snippet)
====================== */

const headerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: 12,
  marginBottom: 12,
};

const commandBarWrapStyle: React.CSSProperties = {
  position: "sticky",
  top: 0,
  zIndex: 20,
  background: "#f2f3f5",
  paddingBottom: 10,
  marginBottom: 12,
};

const commandBarStyle: React.CSSProperties = {
  border: "1px solid #e0e0e0",
  background: "#fff",
  borderRadius: 12,
  padding: 10,
  display: "grid",
  gridTemplateColumns: "minmax(0,1fr) 1fr auto",
  gap: 12,
  alignItems: "center",
};

const leftGroupStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  minWidth: 0, // важно: не раздуваем строку
};

const rightGroupStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  justifyContent: "flex-end",
  flexShrink: 0,
};


const kvRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 14,
  flexWrap: "nowrap",
  alignItems: "flex-start",
  overflowX: "auto",
  overflowY: "hidden",
  WebkitOverflowScrolling: "touch",
};

const iconBtnStyle = (disabled?: boolean): React.CSSProperties => ({
  width: 34,
  height: 32,
  borderRadius: 8,
  border: "1px solid #d1d5db",
  background: "#fff",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
});

const btnPrimaryStyle = (disabledByState?: boolean): React.CSSProperties => ({
  height: 32,
  padding: "0 14px",
  borderRadius: 8,
  border: "1px solid #1f3a8a",
  background: "#1f3a8a",
  color: "#fff",
  cursor: disabledByState ? "not-allowed" : "pointer",
  fontWeight: 600,
  fontSize: 13,
  opacity: disabledByState ? 0.55 : 1,
  whiteSpace: "nowrap",
});

const btnSecondaryStyle = (disabledByState?: boolean): React.CSSProperties => ({
  height: 32,
  padding: "0 14px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#111827",
  cursor: disabledByState ? "not-allowed" : "pointer",
  fontWeight: 600,
  fontSize: 13,
  opacity: disabledByState ? 0.55 : 1,
  whiteSpace: "nowrap",
});

const bannerWarnStyle: React.CSSProperties = {
  marginTop: 8,
  border: "1px solid #e5e7eb",
  borderLeft: "4px solid #d97706",
  background: "#ffffff",
  padding: "10px 12px",
  borderRadius: 12,
  fontSize: 13,
  color: "#111827",
  boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
};

const bannerErrorStyle: React.CSSProperties = {
  marginTop: 8,
  border: "1px solid #fecaca",
  borderLeft: "4px solid #ef4444",
  background: "#fff",
  padding: "10px 12px",
  borderRadius: 12,
  fontSize: 13,
  color: "#111827",
  boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
};

// not used here, but kept identical naming set (UploadBatch has it)
const bannerOcrStyle: React.CSSProperties = {
  marginTop: 8,
  border: "1px solid #ff8a00",
  background: "#fff3e0",
  padding: "10px 12px",
  borderRadius: 10,
  fontSize: 13,
  color: "#161616",
};

const sectionHeadStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: 12,
  margin: "10px 0 8px",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: "#111827",
};

const sectionMetaStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#6b7280",
};

const tableCardStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  background: "#fff",
  padding: 8,
  boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
  minWidth: 0,
  overflow: "hidden",
};

const statusBadgeNeutralStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#374151",
  border: "1px solid #e5e7eb",
  background: "#f9fafb",
  padding: "6px 10px",
  borderRadius: 999,
  whiteSpace: "nowrap",
};

const statusBadgeInfoStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#0b1f4b",
  border: "1px solid #c7d2fe",
  background: "#eef2ff",
  padding: "6px 10px",
  borderRadius: 999,
  whiteSpace: "nowrap",
};

const statusBadgeSuccessStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#064e3b",
  border: "1px solid #a7f3d0",
  background: "#ecfdf5",
  padding: "6px 10px",
  borderRadius: 999,
  whiteSpace: "nowrap",
};

const statusBadgeDangerStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#7f1d1d",
  border: "1px solid #fecaca",
  background: "#fef2f2",
  padding: "6px 10px",
  borderRadius: 999,
  whiteSpace: "nowrap",
};
