// frontend/src/components/ItemsTable.tsx

import React, { useCallback } from "react";
import type { BatchItem, ConsumerCategory, DDMMYYYY } from "../types";
import type { DraftItem } from "../hooks/useFileUpload";
import { Copy, CopyPlus, Trash2, RotateCcw, Download, GripVertical } from "lucide-react";

/* ======================
   Props (discriminated)
====================== */

export interface ItemsTableDraftProps {
  mode: "draft";
  items: DraftItem[];
  disabled?: boolean;

  onRemove: (clientFileId: string) => void;
  onUpdateParams: (
    clientFileId: string,
    patch: Partial<{
      category: ConsumerCategory;
      rate_percent: number;
      overdue_day: number;
      calc_date: DDMMYYYY;
      exclude_zero_debt_periods: boolean;
    }>,
  ) => void;

  onCopyDown?: (clientFileId: string) => void;
  onCopyToAll?: (clientFileId: string) => void;
  onMoveUp?: (clientFileId: string) => void;
  onMoveDown?: (clientFileId: string) => void;
  onReset?: (clientFileId: string) => void;
}

export interface ItemsTableStatusProps {
  mode: "status";
  items: BatchItem[];
  onDownloadItemXlsx?: (itemId: string, filename: string) => Promise<void>;
  onDownloadItemPdf?: (itemId: string, filename: string) => Promise<void>;
}

export type ItemsTableProps = ItemsTableDraftProps | ItemsTableStatusProps;

/* ======================
   Root component
====================== */

export function ItemsTable(props: ItemsTableProps) {
  if (props.mode === "status") {
    return (
      <StatusTable
        items={props.items}
        onDownloadItemXlsx={props.onDownloadItemXlsx}
        onDownloadItemPdf={props.onDownloadItemPdf}
      />
    );
  }
  return <DraftTable {...props} />;
}

/* ======================
   Draft table
====================== */

function DraftTable(props: ItemsTableDraftProps) {
  const { items } = props;
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);

  const [draggingId, setDraggingId] = React.useState<string | null>(null);
  const [dragOverId, setDragOverId] = React.useState<string | null>(null);

  const canReorder = Boolean(props.onMoveUp && props.onMoveDown) && !props.disabled;

  const reorder = React.useCallback(
    (fromIndex: number, toIndex: number) => {
      if (!props.onMoveUp || !props.onMoveDown) return;
      if (fromIndex === toIndex) return;
      if (fromIndex < 0 || toIndex < 0) return;
      if (fromIndex >= items.length || toIndex >= items.length) return;

      const id = items[fromIndex]?.clientFileId;
      if (!id) return;

      const steps = Math.abs(toIndex - fromIndex);
      if (steps === 0) return;
      const move = toIndex < fromIndex ? props.onMoveUp : props.onMoveDown;
      for (let i = 0; i < steps; i++) move(id);
    },
    [items, props.onMoveUp, props.onMoveDown],
  );

  return (
    <div style={{ width: "100%", minWidth: 0, overflowX: "hidden" }}>
      <table style={draftTableStyle}>
        <colgroup>
          <col style={{ width: 44 }} />
          <col />
          <col style={{ width: 220 }} />
          <col style={{ width: 150 }} />
          <col style={{ width: 190 }} />
          <col style={{ width: 160 }} />
        </colgroup>

        <DraftHeader />

        <tbody>
          {items.map((item, idx) => (
            <DraftRow
              key={item.clientFileId}
              item={item}
              index={idx}
              itemsCount={items.length}
              isHovered={hoveredId === item.clientFileId}
              onHover={(v) => setHoveredId(v ? item.clientFileId : null)}
              canReorder={canReorder}
              draggingId={draggingId}
              dragOverId={dragOverId}
              setDraggingId={setDraggingId}
              setDragOverId={setDragOverId}
              reorder={reorder}
              {...props}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DraftHeader() {
  return (
    <thead>
      <tr>
        <th style={{ ...thStyle, width: 44 }} />
        <th style={thStyle}>Файл / Должник</th>
        <th style={thStyle}>Категория</th>
        <th style={thStyle}>Учетная ставка, %</th>
        <th style={thStyle}>День начала просрочки</th>
        <th style={thStyle}>Действия</th>
      </tr>
    </thead>
  );
}

function DraftRow(
  props: ItemsTableDraftProps & {
    item: DraftItem;
    index: number;
    itemsCount: number;
    isHovered: boolean;
    onHover: (v: boolean) => void;

    canReorder: boolean;
    draggingId: string | null;
    dragOverId: string | null;
    setDraggingId: (v: string | null) => void;
    setDragOverId: (v: string | null) => void;
    reorder: (fromIndex: number, toIndex: number) => void;
  },
) {
  const {
    item,
    disabled,
    onRemove,
    onUpdateParams,
    onCopyDown,
    onCopyToAll,
    onReset,
    index,
    itemsCount,
    isHovered,
    onHover,
    canReorder,
    draggingId,
    dragOverId,
    setDraggingId,
    setDragOverId,
    reorder,
  } = props;

  const patch = useCallback(
    (p: Partial<DraftItem["params"]>) => {
      onUpdateParams(item.clientFileId, p);
    },
    [item.clientFileId, onUpdateParams],
  );

  const DEFAULT_RATE = 9.5;
  const DEFAULT_OVERDUE_DAY = 19;

  React.useEffect(() => {
    const rp = item.params.rate_percent;
    const od = item.params.overdue_day;

    const rpInvalid = rp == null || !Number.isFinite(rp) || rp <= 0 || rp === 9;
    if (rpInvalid) patch({ rate_percent: DEFAULT_RATE });

    const odInvalid = od == null || !Number.isFinite(od) || od < 1 || od > 31 || od === 1;
    if (odInvalid) patch({ overdue_day: DEFAULT_OVERDUE_DAY });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.params.rate_percent, item.params.overdue_day]);

  const [rateText, setRateText] = React.useState<string>(() => String(item.params.rate_percent ?? DEFAULT_RATE));

  React.useEffect(() => {
    setRateText(String(item.params.rate_percent ?? DEFAULT_RATE));
  }, [item.params.rate_percent]);

  const isLast = index === itemsCount - 1;

  const isDragging = draggingId === item.clientFileId;
  const isDragOver = dragOverId === item.clientFileId;

  return (
    <tr
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      style={{
        ...(isHovered ? draftRowHoverStyle : null),
        ...(isDragging ? draftRowDraggingStyle : null),
        ...(isDragOver ? draftRowDragOverStyle : null),
      }}
      onDragOver={(e) => {
        if (!canReorder) return;
        e.preventDefault();
        if (dragOverId !== item.clientFileId) setDragOverId(item.clientFileId);
      }}
      onDrop={(e) => {
        if (!canReorder) return;
        e.preventDefault();
        const raw = e.dataTransfer.getData("text/plain");
        const from = Number(raw);
        if (!Number.isFinite(from)) return;
        reorder(from, index);
        setDragOverId(null);
        setDraggingId(null);
      }}
    >
      <td style={{ ...tdStyle, paddingLeft: 6, paddingRight: 6 }}>
        <DragHandle
          enabled={canReorder && !(disabled || itemsCount < 2)}
          onDragStart={(e) => {
            if (!canReorder) return;
            e.dataTransfer.setData("text/plain", String(index));
            e.dataTransfer.effectAllowed = "move";
            setDraggingId(item.clientFileId);
          }}
          onDragEnd={() => {
            setDraggingId(null);
            setDragOverId(null);
          }}
        />
      </td>

      <td style={tdStyle}>
        <div style={fileNameLineStyle} title={item.file.name}>
          {item.file.name}
        </div>
        <div style={debtorLineStyle}>{item.debtor.name ?? "—"}</div>
        <div style={innLineStyle}>ИНН: {item.debtor.inn ?? "—"}</div>
      </td>

      <td style={tdStyle}>
        <select
          value={item.params.category}
          disabled={disabled}
          onChange={(e) => patch({ category: e.target.value as ConsumerCategory })}
          style={selectStyle}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </td>

      <td style={tdStyle}>
        <input
          type="text"
          inputMode="decimal"
          value={rateText}
          disabled={disabled}
          onChange={(e) => setRateText(e.target.value)}
          onBlur={() => {
            const raw = rateText.trim();
            if (!raw) {
              setRateText(String(item.params.rate_percent ?? DEFAULT_RATE));
              return;
            }

            const normalized = raw.replace(",", ".").replace(/\s+/g, "");
            const n = Number(normalized);
            if (!Number.isFinite(n)) {
              setRateText(String(item.params.rate_percent ?? DEFAULT_RATE));
              return;
            }

            patch({ rate_percent: n });
          }}
          style={inputStyle}
        />
      </td>

      <td style={tdStyle}>
        <select
          value={item.params.overdue_day ?? DEFAULT_OVERDUE_DAY}
          disabled={disabled}
          onChange={(e) => patch({ overdue_day: Number(e.target.value) })}
          style={selectStyle}
        >
          {OVERDUE_DAYS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </td>

      <td style={tdStyle}>
        <div style={actionsRowStyle}>
          <div style={actionsGroupStyle}>
            <IconBtn title="Копировать вниз" disabled={disabled || isLast || !onCopyDown} onClick={() => onCopyDown?.(item.clientFileId)}>
              <Copy size={16} />
            </IconBtn>
            <IconBtn title="Копировать всем" disabled={disabled || !onCopyToAll} onClick={() => onCopyToAll?.(item.clientFileId)}>
              <CopyPlus size={16} />
            </IconBtn>
          </div>

          <div style={actionsSeparatorStyle} />

          <div style={actionsGroupStyle}>
            <IconBtn title="Сброс" disabled={disabled || !onReset} onClick={() => onReset?.(item.clientFileId)}>
              <RotateCcw size={16} />
            </IconBtn>
            <IconBtn title="Удалить" variant="danger" disabled={disabled} onClick={() => onRemove(item.clientFileId)}>
              <Trash2 size={16} />
            </IconBtn>
          </div>
        </div>
      </td>
    </tr>
  );
}

const draftRowHoverStyle: React.CSSProperties = { background: "#f1f5f9" };
const draftRowDraggingStyle: React.CSSProperties = { opacity: 0.85 };
const draftRowDragOverStyle: React.CSSProperties = { outline: "2px solid #c7d2fe", outlineOffset: -2 };

/* ======================
   Status table
====================== */

function StatusTable(props: {
  items: BatchItem[];
  onDownloadItemXlsx?: (itemId: string, filename: string) => Promise<void>;
  onDownloadItemPdf?: (itemId: string, filename: string) => Promise<void>;
}) {
  const { items } = props;
  const onDownloadItemXlsx = props.onDownloadItemXlsx;
  const onDownloadItemPdf = props.onDownloadItemPdf;
  const [hoveredKey, setHoveredKey] = React.useState<string | null>(null);

  return (
    <div style={{ overflowX: "hidden", minWidth: 0 }}>
      <table style={draftTableStyle}>
        <colgroup>
          <col />
          <col style={{ width: 120 }} />
          <col />
          <col style={{ width: 140 }} />
          <col style={{ width: 220 }} />
          <col style={{ width: 180 }} />
          <col style={{ width: 150 }} />
        </colgroup>
        <thead>
          <tr>
            <th style={thStyle}>Файл</th>
            <th style={thStyle}>Статус</th>
            <th style={thStyle}>Наименование</th>
            <th style={thStyle}>ИНН</th>
            <th style={thStyle}>Параметры</th>
            <th style={thStyle}>Предупреждения</th>
            <th style={thStyle}>Файлы</th>
          </tr>
        </thead>

        <tbody>
          {items.map((item, idx) => {
            const itemId = (item as any).item_id as string | undefined;
            const fileName = ((item as any).file_name ?? "—") as string;
            const statusText = ((item as any).status ?? "—") as string;

            const debtorName = (item as any).debtor?.name ?? "—";
            const debtorInn = (item as any).debtor?.inn ?? "—";

            const params = (item as any).params;
            const paramsText =
              params && params.category && params.rate_percent != null && params.overdue_day != null
                ? `${params.category}, ${params.rate_percent}%, день ${params.overdue_day}`
                : "—";

            const warnings = ((item as any).warnings ?? []) as string[];
            const itemError = ((item as any).error ?? "") as string;
            const xlsxPath = (item as any).xlsx_path as string | undefined;
            const xlsxReady = Boolean(xlsxPath);

            const rowKey = (itemId ?? fileName) + "_" + idx;
            const isHovered = hoveredKey === rowKey;

            return (
              <tr
                key={rowKey}
                onMouseEnter={() => setHoveredKey(rowKey)}
                onMouseLeave={() => setHoveredKey(null)}
                style={isHovered ? draftRowHoverStyle : undefined}
              >
                <td style={tdStyle}>{fileName}</td>
                <td style={tdStyle}>
                  <StatusIndicator status={statusText} />
                </td>
                <td style={tdStyle}>{debtorName}</td>
                <td style={tdStyle}>{debtorInn}</td>
                <td style={tdStyle}>{paramsText}</td>
                <td style={tdStyle}>
                  {statusText === "ERROR" && itemError ? (
                    <span style={errorTextStyle}>{itemError}</span>
                  ) : warnings.length ? (
                    warnings.join("; ")
                  ) : (
                    "—"
                  )}
                </td>
                <td style={tdStyle}>
                  {itemId && xlsxReady && (onDownloadItemXlsx || onDownloadItemPdf) ? (
                    <div style={filesCellWrapStyle}>
                      {onDownloadItemXlsx ? (
                        <button
                          type="button"
                          onClick={() => void onDownloadItemXlsx(itemId, fileName)}
                          style={xlsxLinkStyle}
                          title="Скачать XLSX"
                        >
                          <Download size={14} />
                          <span style={xlsxLinkTextStyle}>XLSX</span>
                        </button>
                      ) : null}

                      {onDownloadItemPdf ? (
                        <button
                          type="button"
                          onClick={() => void onDownloadItemPdf(itemId, fileName)}
                          style={pdfLinkStyle}
                          title="Скачать PDF (из XLSX)"
                        >
                          <Download size={14} />
                          <span style={xlsxLinkTextStyle}>PDF</span>
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <span style={dashMutedStyle}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ======================
   Helpers / styles
====================== */

const CATEGORIES: ConsumerCategory[] = [
  "Прочие",
  "ТСЖ, ЖСК, ЖК",
  "УК",
  "Собственники жилых помещений в МКД",
  "Собственники нежилых помещений в МКД",
];

const OVERDUE_DAYS: number[] = Array.from({ length: 31 }, (_, i) => i + 1);

type IconBtnVariant = "default" | "danger";

function DragHandle(props: {
  enabled: boolean;
  onDragStart: React.DragEventHandler<HTMLButtonElement>;
  onDragEnd: React.DragEventHandler<HTMLButtonElement>;
}) {
  const { enabled, onDragStart, onDragEnd } = props;
  const [hover, setHover] = React.useState(false);

  return (
    <button
      type="button"
      draggable={enabled}
      title={enabled ? "Перетащите для изменения порядка" : ""}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      disabled={!enabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: 30,
        height: 30,
        borderRadius: 6,
        border: hover && enabled ? "1px solid #e5e7eb" : "1px solid transparent",
        background: hover && enabled ? "#f8fafc" : "transparent",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#6b7280",
        cursor: enabled ? "grab" : "not-allowed",
        opacity: enabled ? 1 : 0.35,
        userSelect: "none",
      }}
    >
      <GripVertical size={16} />
    </button>
  );
}

function IconBtn(props: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
  variant?: IconBtnVariant;
}) {
  const { title, onClick, children, disabled, variant = "default" } = props;
  const [hover, setHover] = React.useState(false);
  const s = getIconBtnStyle({ hover, disabled: !!disabled, variant });

  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      style={s}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {children}
    </button>
  );
}

function getIconBtnStyle(opts: { hover: boolean; disabled: boolean; variant: IconBtnVariant }): React.CSSProperties {
  const { hover, disabled, variant } = opts;

  const base: React.CSSProperties = {
    width: 30,
    height: 30,
    borderRadius: 6,
    border: "1px solid transparent",
    background: "transparent",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    color: variant === "danger" ? "#b91c1c" : "#111827",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.45 : 1,
    transition: "background 120ms ease, border-color 120ms ease",
  };

  if (disabled) return base;

  if (hover) {
    if (variant === "danger") {
      return { ...base, background: "#fef2f2", border: "1px solid #fecaca" };
    }
    return { ...base, background: "#f8fafc", border: "1px solid #e5e7eb" };
  }

  return base;
}

const draftTableStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: "100%",
  borderCollapse: "collapse",
  minWidth: 0,
  tableLayout: "fixed",
  fontFamily: "Arial, sans-serif",
  fontSize: 13,
  lineHeight: 1.25,
  color: "#111827",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: "100%",
  borderCollapse: "collapse",
  minWidth: 0,
  tableLayout: "fixed",
  fontFamily: "Arial, sans-serif",
  fontSize: 13,
  lineHeight: 1.25,
  color: "#111827",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  fontSize: 12,
  fontWeight: 700,
  color: "#111827",
  padding: "10px 12px",
  background: "#e4e7ec",
  borderBottom: "1px solid #cfd6df",
  whiteSpace: "nowrap",
  overflow: "visible",
  textOverflow: "clip",
  fontFamily: "Arial, sans-serif",
  lineHeight: 1.25,
};

const tdStyle: React.CSSProperties = {
  padding: "10px 10px",
  borderBottom: "1px solid #e5e7eb",
  verticalAlign: "top",
  fontFamily: "Times New Roman, sans-serif",
  fontSize: 13,
  lineHeight: 1.25,
  color: "#111827",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 30,
  padding: "0 8px",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  height: 30,
  padding: "0 8px",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  outline: "none",
};

const fileNameLineStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: 13,
  color: "#111827",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const debtorLineStyle: React.CSSProperties = {
  marginTop: 4,
  fontSize: 12,
  color: "#374151",
  whiteSpace: "normal",
  wordBreak: "break-word",
};

const innLineStyle: React.CSSProperties = {
  marginTop: 2,
  fontSize: 11,
  color: "#9ca3af",
};

const actionsRowStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "flex-start",
  gap: 10,
};

const actionsGroupStyle: React.CSSProperties = {
  display: "inline-flex",
  gap: 6,
};

const actionsSeparatorStyle: React.CSSProperties = {
  width: 1,
  alignSelf: "stretch",
  background: "#e5e7eb",
};

/* ======================
   Status UI helpers
====================== */

function StatusIndicator(props: { status: string }) {
  const s = String(props.status ?? "").toUpperCase();
  const color = statusDotColor(s);
  return (
    <span style={statusWrapStyle}>
      <span style={{ ...statusDotStyle, background: color }} />
      <span style={statusTextStyle}>{s || "—"}</span>
    </span>
  );
}

function statusDotColor(statusUpper: string): string {
  if (statusUpper === "DONE" || statusUpper === "SUCCESS") return "#16a34a";
  if (statusUpper === "ERROR" || statusUpper === "FAILED") return "#dc2626";
  return "#9ca3af";
}

const statusWrapStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  whiteSpace: "nowrap",
};

const statusDotStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  borderRadius: 999,
  display: "inline-block",
};

const statusTextStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 500,
  color: "#111827",
};

const xlsxLinkStyle: React.CSSProperties = {
  border: "none",
  background: "transparent",
  color: "#2563eb",
  cursor: "pointer",
  padding: 0,
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
};

const pdfLinkStyle: React.CSSProperties = {
  ...xlsxLinkStyle,
  color: "#111827",
};

const filesCellWrapStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 12,
};

const xlsxLinkTextStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: 0.2,
  textDecoration: "underline",
  textUnderlineOffset: 2,
};

const dashMutedStyle: React.CSSProperties = { color: "#9ca3af" };

const errorTextStyle: React.CSSProperties = {
  color: "#b91c1c",
  fontWeight: 600,
};