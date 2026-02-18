import React, { useEffect, useMemo, useRef } from "react";
import { CalendarDays, RefreshCcw, Plus, Trash2 } from "lucide-react";
import { FileDrop } from "../components/FileDrop";
import { ItemsTable } from "../components/ItemsTable";
import type { DDMMYYYY } from "../types";
import { useFileUpload } from "../hooks/useFileUpload";

export interface UploadBatchProps {
  onBatchCreated: (batchId: string) => void;
}

export function UploadBatch(props: UploadBatchProps) {
  const { onBatchCreated } = props;
  const { state, actions } = useFileUpload();

  const disabled = state.phase === "processing";
  const hasItems = state.items.length > 0;

  const batchCalcDate = useMemo(() => state.items[0]?.params.calc_date ?? "", [state.items]);
  const batchExcludeZero = useMemo(
    () => state.items[0]?.params.exclude_zero_debt_periods ?? false,
    [state.items],
  );

  const mergeXlsx = state.mergeXlsx;
  const showMerge = state.items.length > 1;

  const applyToAll = (patch: Partial<{ calc_date: DDMMYYYY; exclude_zero_debt_periods: boolean }>) => {
    for (const it of state.items) actions.updateItemParams(it.clientFileId, patch);
  };

  const lastInspectCountRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const count = state.items.length;
    if (count === 0) {
      lastInspectCountRef.current = 0;
      return;
    }
    if (count > lastInspectCountRef.current) {
      lastInspectCountRef.current = count;
      actions.runInspect().catch(console.error);
    }
  }, [state.items.length, actions]);

  const openFileDialog = () => {
    if (disabled) return;
    fileInputRef.current?.click();
  };

  const onClearAll = () => {
    if (disabled) return;
    const ok = window.confirm("Очистить список файлов? Все загруженные справки будут удалены из набора.");
    if (!ok) return;
    actions.clearAll();
  };

  const mergeBlockedByInn = state.innMismatch.hasMismatch;
  const mergeEnabled = showMerge && !mergeBlockedByInn;

  // OCR warnings come strictly from inspect response fields (no heuristics on the client).
  const ocrItems = useMemo(() => {
    return state.items
      .map((it) => {
        const anyIt = it as any;
        const needs = Boolean(anyIt.needs_ocr ?? anyIt.inspect?.needs_ocr);
        const msg = (anyIt.inspect_warning ?? anyIt.inspect?.inspect_warning) as string | undefined;
        return needs ? { clientFileId: it.clientFileId, filename: it.file.name, message: msg } : null;
      })
      .filter(Boolean) as Array<{ clientFileId: string; filename: string; message?: string }>;
  }, [state.items]);

  return (
    <div style={{ minWidth: 0 }}>
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Загрузка справок</div>
          <div style={{ fontSize: 13, color: "#525252", lineHeight: 1.35 }}>
            Загрузите PDF-справки о задолженности. Проверьте должника и задайте параметры — затем сформируйте расчет пени
            в XLSX.
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            onClick={openFileDialog}
            disabled={disabled}
            title="Добавить файлы"
            style={iconTopBtnStyle(disabled)}
          >
            <Plus size={18} />
          </button>

          <button
            type="button"
            onClick={onClearAll}
            disabled={disabled || !hasItems}
            title="Очистить список файлов"
            style={iconDangerTopBtnStyle(disabled || !hasItems)}
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          if (!e.target.files) return;
          actions.addFiles(Array.from(e.target.files));
          e.target.value = "";
        }}
      />

      {!hasItems && (
        <div style={{ marginBottom: 16 }}>
          <FileDrop multiple accept="application/pdf" disabled={disabled} onFiles={(files) => actions.addFiles(files)} />
        </div>
      )}

      {hasItems && (
        <>
          {/* Command bar */}
          <div style={commandBarWrapStyle}>
            <div style={commandBarStyle}>
              <div style={leftGroupStyle}>
                <div style={dateRowStyle}>
                  <span style={dateLabelStyle}>Дата расчёта</span>
                  <DateInput
                    value={batchCalcDate}
                    disabled={disabled}
                    onChange={(v) => applyToAll({ calc_date: v as DDMMYYYY })}
                  />
                </div>

                <div style={paramRowStyle}>
                  <ParamCheckbox
                    label="Исключить периоды с нулевым долгом"
                    checked={batchExcludeZero}
                    disabled={disabled}
                    onChange={(checked) => applyToAll({ exclude_zero_debt_periods: checked })}
                  />

                  {showMerge && (
                    <ParamCheckbox
                      label={
                        mergeBlockedByInn
                          ? "Объединить в один XLSX (недоступно: разные ИНН)"
                          : "Объединить в один XLSX (если должник один)"
                      }
                      checked={mergeXlsx}
                      disabled={disabled || !mergeEnabled}
                      onChange={(checked) => actions.setMergeXlsx(checked)}
                    />
                  )}
                </div>
              </div>

              <div style={rightGroupStyle}>
                <button
                  type="button"
                  onClick={() => void actions.runInspect()}
                  disabled={disabled}
                  title="Обновить извлечение (Наименование/ИНН)"
                  style={iconBtnStyle(disabled)}
                >
                  <RefreshCcw size={18} />
                </button>

                <button
                  type="button"
                  onClick={async () => {
                    const res = await actions.processBatch();
                    onBatchCreated(res.batchId);
                  }}
                  disabled={!state.canProcess}
                  style={btnPrimaryStyle(!state.canProcess)}
                  title={!state.canProcess ? "Проверьте обязательные поля и дождитесь завершения извлечения" : ""}
                >
                  Сформировать расчёт
                </button>
              </div>
            </div>

            {state.innMismatch.hasMismatch && (
              <div style={bannerWarnStyle}>
                <span style={{ fontWeight: 700 }}>Разные ИНН.</span>&nbsp;Объединение в один XLSX недоступно. ИНН:{" "}
                {state.innMismatch.inns.join(", ")}.
              </div>
            )}

            {ocrItems.length > 0 && (
              <div style={bannerOcrStyle}>
                <div style={{ fontWeight: 700 }}>{ocrItems.length} файл(ов) требуют OCR и не будут обработаны</div>
                <div style={{ marginTop: 6, display: "grid", gap: 4 }}>
                  {ocrItems.map((x) => (
                    <div key={x.clientFileId} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                      <span style={{ fontWeight: 700 }}>{x.filename}:</span>
                      <span style={{ whiteSpace: "pre-wrap" }}>
                        {x.message ?? "В PDF отсутствует текстовый слой (похоже на скан). Нужен OCR."}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {state.globalError && (
              <div style={bannerErrorStyle}>
                <span style={{ fontWeight: 700 }}>Ошибка.</span>&nbsp;
                <span style={{ whiteSpace: "pre-wrap" }}>{state.globalError}</span>
              </div>
            )}
          </div>

          {/* Section header (Status moved here) */}
          <div style={sectionHeadStyle}>
            <div style={sectionTitleStyle}>Справки</div>

            <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
              <div style={sectionMetaStyle}>Всего: {state.items.length}</div>
              <StatusBadge phase={state.phase} />
            </div>
          </div>

          <div style={tableCardStyle}>
            <ItemsTable
              mode="draft"
              items={state.items}
              disabled={disabled}
              onRemove={actions.removeItem}
              onUpdateParams={actions.updateItemParams}
              onReset={actions.resetParams}
              onCopyDown={actions.copyDown}
              onCopyToAll={actions.copyToAll}
              onMoveUp={actions.moveUp}
              onMoveDown={actions.moveDown}
            />
          </div>
        </>
      )}
    </div>
  );
}

/* ======================
   DateInput
====================== */

function isDDMMYYYY(v: string): v is DDMMYYYY {
  return /^\d{2}\.\d{2}\.\d{4}$/.test(v);
}

function DateInput(props: { value: string; disabled?: boolean; onChange: (v: DDMMYYYY) => void }) {
  const { value, disabled, onChange } = props;

  const [text, setText] = React.useState<string>(value);
  const nativeRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    setText(value);
  }, [value]);

  const commitIfValid = (raw: string) => {
    const v = raw.trim();
    if (!v) {
      setText(value);
      return;
    }
    if (!isDDMMYYYY(v)) {
      setText(value);
      return;
    }
    onChange(v as DDMMYYYY);
  };

  const openNativePicker = () => {
    if (disabled) return;
    const el = nativeRef.current;
    if (!el) return;

    const parsed = parseDDMMYYYY(text);
    if (parsed) {
      el.value = `${parsed.year}-${String(parsed.month).padStart(2, "0")}-${String(parsed.day).padStart(2, "0")}`;
    } else {
      const t = new Date();
      el.value = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
    }

    const anyEl = el as any;
    if (typeof anyEl.showPicker === "function") {
      anyEl.showPicker();
      return;
    }
    el.focus();
    el.click();
  };

  return (
    <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <input
        type="text"
        value={text}
        disabled={disabled}
        placeholder="ДД.ММ.ГГГГ"
        inputMode="numeric"
        onChange={(e) => setText(e.target.value)}
        onBlur={() => commitIfValid(text)}
        style={{ ...inputStyle, paddingRight: 34 }}
      />

      <button
        type="button"
        onClick={openNativePicker}
        title="Выбрать дату"
        aria-disabled={disabled ? "true" : "false"}
        style={dateBtnStyle(disabled)}
      >
        <CalendarDays size={16} />
      </button>

      <input
        ref={nativeRef}
        type="date"
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        style={{ position: "absolute", opacity: 0, pointerEvents: "none", width: 0, height: 0 }}
        onChange={(e) => {
          const iso = e.target.value;
          if (!iso) return;
          const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
          if (!m) return;
          const yyyy = m[1];
          const mm = m[2];
          const dd = m[3];
          const v = `${dd}.${mm}.${yyyy}` as DDMMYYYY;
          setText(v);
          onChange(v);
        }}
      />
    </div>
  );
}

function parseDDMMYYYY(v: string): { day: number; month: number; year: number } | null {
  const m = v.trim().match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!m) return null;
  const day = Number(m[1]);
  const month = Number(m[2]);
  const year = Number(m[3]);
  if (!Number.isFinite(day) || !Number.isFinite(month) || !Number.isFinite(year)) return null;
  if (month < 1 || month > 12) return null;
  const dim = new Date(year, month, 0).getDate();
  if (day < 1 || day > dim) return null;
  return { day, month, year };
}

/* ======================
   ParamCheckbox
====================== */

function ParamCheckbox(props: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const { label, checked, disabled, onChange } = props;

  return (
    <label
      title={label}
      style={{
        ...paramCheckboxWrapStyle,
        ...(checked ? paramCheckboxWrapActiveStyle : null),
        ...(disabled ? paramCheckboxWrapDisabledStyle : null),
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={paramCheckboxInputStyle}
      />
      <span style={paramCheckboxLabelStyle}>{label}</span>
    </label>
  );
}

/* ======================
   Status badge (colored)
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
   Styles
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
  gridTemplateColumns: "minmax(0,1fr) auto",
  gap: 12,
  alignItems: "center",
};

const leftGroupStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "row",
  alignItems: "center",
  gap: 14,
  flexWrap: "wrap",
  minWidth: 0,
};

const dateRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  minWidth: 0,
};

const dateLabelStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: "#161616",
  whiteSpace: "nowrap",
};

const paramRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  flexWrap: "wrap",
};

const rightGroupStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  justifyContent: "flex-end",
  flexShrink: 0,
};

const inputStyle: React.CSSProperties = {
  padding: "0 10px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  fontSize: 13,
  minWidth: 130,
  height: 28,
  lineHeight: "28px",
};

const dateBtnStyle = (disabled?: boolean): React.CSSProperties => ({
  position: "absolute",
  right: 6,
  top: "50%",
  transform: "translateY(-50%)",
  width: 24,
  height: 24,
  borderRadius: 7,
  border: "none",
  background: "transparent",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  opacity: disabled ? 0.45 : 0.75,
  cursor: disabled ? "not-allowed" : "pointer",
});

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

const iconTopBtnStyle = (disabled?: boolean): React.CSSProperties => ({
  width: 36,
  height: 36,
  borderRadius: 10,
  border: "1px solid #c6c6c6",
  background: "#fff",
  color: "#161616",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
});

const iconDangerTopBtnStyle = (disabled?: boolean): React.CSSProperties => ({
  width: 36,
  height: 36,
  borderRadius: 10,
  border: "1px solid #da1e28",
  background: "#fff1f1",
  color: "#da1e28",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.55 : 1,
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

/* чекбоксы параметров */

const paramCheckboxWrapStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  borderRadius: 10,
  border: "1px solid #d1d5db",
  background: "#fff",
  cursor: "pointer",
  userSelect: "none",
  transition: "background 120ms ease, border-color 120ms ease",
};

const paramCheckboxWrapActiveStyle: React.CSSProperties = {
  background: "#eef2ff",
  borderColor: "#c7d2fe",
};

const paramCheckboxWrapDisabledStyle: React.CSSProperties = {
  opacity: 0.5,
  cursor: "not-allowed",
};

const paramCheckboxInputStyle: React.CSSProperties = {
  width: 16,
  height: 16,
  margin: 0,
  accentColor: "#1f3a8a",
};

const paramCheckboxLabelStyle: React.CSSProperties = {
  fontSize: 13,
  color: "#161616",
  whiteSpace: "nowrap",
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
