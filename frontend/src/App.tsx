// frontend/src/App.tsx

import React, { useEffect, useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { UploadBatch } from "./pages/UploadBatch";
import { BatchStatus } from "./pages/BatchStatus";
import type { BatchId } from "./types";

type Page = "upload" | "status";
type RecentBatch = { id: BatchId; ts: number };

const CANVAS_BG = "#f2f3f5";
const SIDEBAR_BG = "#3a4553"; // чуть светлее, “офисный” графит
const SIDEBAR_BG_2 = "#445162";
const SIDEBAR_TEXT = "#eef2f7";
const SIDEBAR_MUTED = "#b9c2cf";

const ACCENT = "#1f3a8a";

const RECENT_KEY = "pdf2xlsx_recent_batches_v1";

function loadRecent(): RecentBatch[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr
      .map((x) => ({ id: String(x?.id ?? ""), ts: Number(x?.ts ?? 0) }))
      .filter((x) => x.id && Number.isFinite(x.ts))
      .slice(0, 10);
  } catch {
    return [];
  }
}

function saveRecent(list: RecentBatch[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 10)));
  } catch {
    // ignore
  }
}

function formatTs(ts: number): string {
  const d = new Date(ts);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
}

function shortId(id: string): string {
  const s = String(id);
  if (s.length <= 14) return s;
  return s.slice(0, 6) + "…" + s.slice(-4);
}

export default function App() {
  const [page, setPage] = useState<Page>("upload");
  const [activeBatchId, setActiveBatchId] = useState<BatchId | null>(null);
  const [recent, setRecent] = useState<RecentBatch[]>(() => loadRecent());

  // убираем “белые поля” браузера без правок глобального CSS
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;

    html.style.height = "100%";
    html.style.width = "100%";
    body.style.height = "100%";
    body.style.width = "100%";
    body.style.margin = "0";
    body.style.padding = "0";
    body.style.background = CANVAS_BG;
    body.style.overflow = "hidden";

    return () => {
      // не восстанавливаем — для SPA это ок
    };
  }, []);

  useEffect(() => {
    setRecent(loadRecent());
  }, []);

  const addRecent = (batchId: BatchId) => {
    const now = Date.now();
    const next = [{ id: batchId, ts: now }, ...recent.filter((r) => r.id !== batchId)].slice(0, 10);
    setRecent(next);
    saveRecent(next);
  };

  const openStatus = (batchId: BatchId) => {
    setActiveBatchId(batchId);
    setPage("status");
  };

  const content = useMemo(() => {
    if (page === "status") {
      if (!activeBatchId) {
        return (
          <div style={{ fontSize: 13, color: "#6b7280" }}>
            Чтобы посмотреть статус обработки, выберите обработку из списка слева.
          </div>
        );
      }
      return <BatchStatus batchId={activeBatchId} />;
    }

    return (
      <UploadBatch
        onBatchCreated={(batchId) => {
          addRecent(batchId);
          openStatus(batchId);
        }}
      />
    );
  }, [activeBatchId, page, recent]);

  return (
    <div style={layoutStyle}>
      <aside style={sidebarStyle}>
        <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 10 }}>
          Сервис расчета пени из PDF
        </div>

        <nav style={{ display: "grid", gap: 8, marginBottom: 12 }}>
          <SidebarLink active={page === "upload"} label="Загрузить файлы" onClick={() => setPage("upload")} />
          <SidebarLink active={page === "status"} label="Статус обработки" onClick={() => setPage("status")} />
        </nav>

        {recent.length > 0 && (
          <div style={sidebarSectionStyle}>
            <div style={sidebarSectionTitle}>Последние обработки</div>

            <div style={{ display: "grid", gap: 6 }}>
              {recent.slice(0, 6).map((r) => (
                <div key={r.id} style={recentRowStyle}>
                  <button
                    type="button"
                    onClick={() => openStatus(r.id)}
                    style={recentBtnStyle}
                    title={r.id}
                  >
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
                      {formatTs(r.ts)}
                    </div>
                    <div style={{ fontSize: 12, color: SIDEBAR_MUTED, marginTop: 2 }}>
                      ID: {shortId(r.id)}
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(r.id)}
                    title="Скопировать ID"
                    style={iconGhostStyle}
                  >
                    <Copy size={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginTop: "auto", fontSize: 12, color: SIDEBAR_MUTED }}>
          © 2026 Сервис расчета пени из PDF. Все права защищены.
        </div>
      </aside>

      <main style={mainStyle}>
        <div style={mainInnerStyle}>{content}</div>
      </main>
    </div>
  );
}

function SidebarLink(props: { active: boolean; label: string; onClick: () => void }) {
  const { active } = props;

  return (
    <button
      type="button"
      onClick={props.onClick}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        borderRadius: 10,
        border: active ? `1px solid ${ACCENT}` : "1px solid rgba(255,255,255,0.10)",
        background: active ? "rgba(31,58,138,0.28)" : "rgba(255,255,255,0.03)",
        color: active ? "#ffffff" : SIDEBAR_TEXT,
        cursor: "pointer",
        fontWeight: 700,
        fontSize: 13,
        position: "relative",
      }}
    >
      {/* Явная активная полоса слева */}
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 6,
          bottom: 6,
          width: 4,
          borderRadius: 999,
          background: active ? "#93c5fd" : "transparent",
        }}
      />
      <span style={{ paddingLeft: 8, display: "inline-block" }}>{props.label}</span>
    </button>
  );
}

const layoutStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "260px 1fr",
  width: "100vw",
  height: "100vh",
  background: CANVAS_BG,
};

const sidebarStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
  padding: 16,
  borderRight: "1px solid rgba(17,24,39,0.35)",
  background: SIDEBAR_BG,
  color: SIDEBAR_TEXT,
  boxSizing: "border-box",
  minWidth: 0,
};

const sidebarSectionStyle: React.CSSProperties = {
  borderTop: "1px solid rgba(255,255,255,0.10)",
  paddingTop: 12,
};

const sidebarSectionTitle: React.CSSProperties = {
  fontSize: 12,
  color: SIDEBAR_MUTED,
  marginBottom: 8,
  fontWeight: 700,
};

const mainStyle: React.CSSProperties = {
  padding: 16,
  background: CANVAS_BG,
  boxSizing: "border-box",
  minWidth: 0,
  overflowX: "hidden", // чтобы таблица не “вылезала” по ширине
  overflowY: "auto",   // ВАЖНО: включаем скролл по высоте
};

const mainInnerStyle: React.CSSProperties = {
  width: "100%",
  minWidth: 0,
  margin: 0,
};

const recentRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "stretch",
  gap: 8,
};

const recentBtnStyle: React.CSSProperties = {
  flex: 1,
  textAlign: "left",
  padding: "8px 10px",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.12)",
  background: SIDEBAR_BG_2,
  cursor: "pointer",
  overflow: "hidden",
};

const iconGhostStyle: React.CSSProperties = {
  width: 34,
  minWidth: 34,
  height: "100%",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.04)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  color: SIDEBAR_TEXT,
};
