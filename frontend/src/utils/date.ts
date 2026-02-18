// frontend/src/utils/date.ts
import type { DDMMYYYY } from "../types";

export function todayDDMMYYYY(): DDMMYYYY {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = String(d.getFullYear());
  return `${dd}.${mm}.${yyyy}` as DDMMYYYY;
}
