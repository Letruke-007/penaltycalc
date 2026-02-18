// frontend/src/hooks/useBatchStatus.ts

import { useEffect, useMemo, useRef, useState } from "react";
import type { Batch, BatchId } from "../types";
import { batchService } from "../services/batchService";
import { ApiError } from "../api/client";

export type BatchStatusPhase = "idle" | "loading" | "polling" | "stable" | "error";

export interface UseBatchStatusState {
  phase: BatchStatusPhase;
  batch?: Batch;
  error?: string;

  progress: {
    total: number;
    done: number;
    errors: number;
  };

  innMismatch: {
    hasMismatch: boolean;
    inns: string[];
  };

  isFinal: boolean;
}

export interface UseBatchStatusActions {
  reload: () => Promise<void>;
}

const FINAL_STATUSES = new Set<Batch["status"]>(["DONE", "ERROR"]);

export function useBatchStatus(batchId: BatchId | null): {
  state: UseBatchStatusState;
  actions: UseBatchStatusActions;
} {
  const [phase, setPhase] = useState<BatchStatusPhase>("idle");
  const [batch, setBatch] = useState<Batch | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  const timerRef = useRef<number | null>(null);
  const attemptRef = useRef<number>(0);

  const isFinal = useMemo(() => (batch ? FINAL_STATUSES.has(batch.status) : false), [batch]);

  const progress = useMemo(() => {
    if (!batch) return { total: 0, done: 0, errors: 0 };
    return {
      total: batch.total_items,
      done: batch.done_items,
      errors: batch.error_items,
    };
  }, [batch]);

  const innMismatch = useMemo(() => {
    const inns = uniqueNonEmpty(
      (batch?.items ?? [])
        .map((it) => it.debtor.inn ?? "")
        .map((x) => x.replace(/\D+/g, "")),
    );
    return { hasMismatch: inns.length > 1, inns };
  }, [batch]);

  const clearTimer = () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const schedule = (ms: number) => {
    clearTimer();
    timerRef.current = window.setTimeout(() => void tick(), ms);
  };

  const backoffMs = (attempt: number) => {
    const seq = [1500, 2500, 4000, 6000, 8000];
    return seq[Math.min(attempt, seq.length - 1)];
  };

  const tick = async () => {
    if (!batchId) return;

    try {
      setError(undefined);

      const data = await batchService.get(batchId);
      setBatch(data);

      if (FINAL_STATUSES.has(data.status)) {
        setPhase("stable");
        attemptRef.current = 0;
        clearTimer();
        return;
      }

      setPhase("polling");
      attemptRef.current += 1;
      schedule(backoffMs(attemptRef.current - 1));
    } catch (e) {
      setError(formatError(e));
      setPhase("error");
      attemptRef.current += 1;
      schedule(Math.min(10_000, 2000 + attemptRef.current * 1000));
    }
  };

  useEffect(() => {
    clearTimer();
    attemptRef.current = 0;

    setBatch(undefined);
    setError(undefined);

    if (!batchId) {
      setPhase("idle");
      return;
    }

    setPhase("loading");
    void tick();

    return () => {
      clearTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const reload = async () => {
    if (!batchId) return;

    clearTimer();
    attemptRef.current = 0;
    setPhase("loading");
    setError(undefined);

    try {
      const data = await batchService.get(batchId);
      setBatch(data);

      if (FINAL_STATUSES.has(data.status)) setPhase("stable");
      else {
        setPhase("polling");
        schedule(1500);
      }
    } catch (e) {
      setError(formatError(e));
      setPhase("error");
    }
  };

  const state: UseBatchStatusState = {
    phase,
    batch,
    error,
    progress,
    innMismatch,
    isFinal,
  };

  return { state, actions: { reload } };
}

function uniqueNonEmpty(values: string[]): string[] {
  const s = new Set<string>();
  for (const v of values) {
    if (!v) continue;
    s.add(v);
  }
  return Array.from(s);
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) return e.message || `HTTP ${e.status}`;
  if (e instanceof Error) return e.message;
  return "Неизвестная ошибка";
}
