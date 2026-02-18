// frontend/src/services/api.ts

import { ApiClient } from "../api/client";

/**
 * Docker (nginx) mode:
 * - frontend served by nginx
 * - nginx proxies /api/* -> http://backend:8000/api/*
 * Therefore default should be same-origin ("").
 *
 * For local dev without proxy you can set VITE_API_BASE_URL, e.g. "http://127.0.0.1:8000".
 */
const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "";

export const api = new ApiClient({
  baseUrl,
  timeoutMs: 120_000,
});
