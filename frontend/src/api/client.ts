// frontend/src/api/client.ts

export class ApiError extends Error {
  public readonly status: number;
  public readonly url: string;
  public readonly code?: string;
  public readonly details?: unknown;

  constructor(args: {
    message: string;
    status: number;
    url: string;
    code?: string;
    details?: unknown;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.url = args.url;
    this.code = args.code;
    this.details = args.details;
  }
}

export interface ApiClientOptions {
  baseUrl: string; // e.g. http://127.0.0.1:8001
  timeoutMs?: number;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(opts: ApiClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = opts.timeoutMs ?? 60_000;
  }

  public async getJson<T>(path: string, init?: RequestInit): Promise<T> {
    return this.requestJson<T>(path, { ...init, method: "GET" });
  }

  public async postJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
    return this.requestJson<T>(path, {
      ...init,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      body: JSON.stringify(body),
    });
  }

  public async postForm<T>(path: string, form: FormData, init?: RequestInit): Promise<T> {
    return this.requestJson<T>(path, {
      ...init,
      method: "POST",
      body: form,
    });
  }

  public async getBlob(path: string, init?: RequestInit): Promise<Blob> {
    const url = this.toUrl(path);
    const res = await this.fetchWithTimeout(url, { ...init, method: "GET" });

    if (!res.ok) {
      const details = await safeReadJson(res);
      throw new ApiError({
        message: `GET ${path} failed`,
        status: res.status,
        url,
        details,
      });
    }
    return res.blob();
  }

    public async getRaw(path: string, init?: RequestInit): Promise<Response> {
    const url = this.toUrl(path);
    const res = await this.fetchWithTimeout(url, { ...init, method: "GET" });

    if (!res.ok) {
      const details = await safeReadJson(res);
      throw new ApiError({
        message: `GET ${path} failed`,
        status: res.status,
        url,
        details,
      });
    }

    return res;
  }

  private async requestJson<T>(path: string, init: RequestInit): Promise<T> {
    const url = this.toUrl(path);
    const res = await this.fetchWithTimeout(url, init);

    if (!res.ok) {
      const details = await safeReadJson(res);
      // Try to extract conventional error shape
      const code =
        isObject(details) && typeof details["code"] === "string" ? (details["code"] as string) : undefined;

      const message =
        isObject(details) && typeof details["message"] === "string"
          ? (details["message"] as string)
          : `${init.method ?? "REQUEST"} ${path} failed`;

      throw new ApiError({
        message,
        status: res.status,
        url,
        code,
        details,
      });
    }

    const data = (await res.json()) as unknown;
    return data as T;
  }

  private toUrl(path: string): string {
    if (!path.startsWith("/")) return `${this.baseUrl}/${path}`;
    return `${this.baseUrl}${path}`;
  }

  private async fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const id = window.setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      window.clearTimeout(id);
    }
  }
}

async function safeReadJson(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined;
  try {
    return (await res.json()) as unknown;
  } catch {
    return undefined;
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}
