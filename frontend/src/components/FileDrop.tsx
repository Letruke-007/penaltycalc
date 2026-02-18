// frontend/src/components/FileDrop.tsx

import React, { useCallback, useRef, useState } from "react";

export interface FileDropProps {
  accept?: string; // e.g. "application/pdf"
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

export function FileDrop(props: FileDropProps) {
  const { accept = "application/pdf", multiple = true, disabled = false, onFiles } = props;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isOver, setIsOver] = useState(false);

  const pickFiles = useCallback(() => {
    if (disabled) return;
    inputRef.current?.click();
  }, [disabled]);

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (disabled) return;
      const list = e.target.files;
      if (!list || list.length === 0) return;
      onFiles(Array.from(list));
      e.target.value = "";
    },
    [disabled, onFiles],
  );

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;
      e.preventDefault();
      setIsOver(true);
    },
    [disabled],
  );

  const onDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;
      e.preventDefault();
      setIsOver(false);
    },
    [disabled],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (disabled) return;
      e.preventDefault();
      setIsOver(false);

      const list = e.dataTransfer.files;
      if (!list || list.length === 0) return;

      onFiles(Array.from(list));
    },
    [disabled, onFiles],
  );

  const borderColor = isOver ? "#0f62fe" : "#c6c6c6";
  const bg = isOver ? "#eef5ff" : "#ffffff";

  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{
        border: `2px dashed ${borderColor}`,
        background: bg,
        padding: 34,
        borderRadius: 14,
        cursor: disabled ? "not-allowed" : "pointer",
        userSelect: "none",
        minHeight: 60,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: isOver ? "0 0 0 4px rgba(15,98,254,0.10)" : "none",
        transition: "box-shadow 120ms ease, background 120ms ease, border-color 120ms ease",
      }}
      onClick={pickFiles}
      role="button"
      aria-disabled={disabled}
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={handleInput}
        style={{ display: "none" }}
      />

      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 8 }}>
          Перетащите PDF-справки сюда
        </div>
        <div style={{ fontSize: 13, color: "#525252" }}>
          или нажмите, чтобы выбрать файлы
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 6 }}>
          Можно загрузить несколько файлов сразу
        </div>
      </div>
    </div>
  );
}
