/**
 * Thin fetch client. Session-cookie auth: the browser sends the HttpOnly session cookie, and we echo the CSRF cookie in
 * X-CSRFToken for unsafe methods. Nothing sensitive is kept in localStorage.
 */
export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  status: number;
  code: string;
  fields: FieldErrors;
  constructor(status: number, code: string, message: string, fields: FieldErrors = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
  get isNetwork() {
    return this.status === 0;
  }
}

const CSRF_COOKIE = "daywell_csrftoken";

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

let csrfPromise: Promise<void> | null = null;
export async function ensureCsrf(): Promise<void> {
  if (readCookie(CSRF_COOKIE)) return;
  csrfPromise ??= fetch("/api/v1/auth/csrf/", { credentials: "same-origin" }).then(() => undefined).finally(() => {
    csrfPromise = null;
  });
  await csrfPromise;
}

type Query = Record<string, string | number | boolean | undefined | null>;

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path;
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function request<T>(method: string, path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (unsafe) await ensureCsrf();
  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (unsafe) headers["X-CSRFToken"] = readCookie(CSRF_COOKIE) ?? "";
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      credentials: "same-origin",
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      ...init,
    });
  } catch {
    throw new ApiError(0, "network", navigator.onLine === false
      ? "You're offline. Changes can't be saved until you reconnect."
      : "We couldn't reach DayWell. Please check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const err = (data && typeof data === "object" && "error" in data ? (data as { error: { code: string; message: string; fields: FieldErrors } }).error : null);
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, err?.code ?? "error", err?.message ?? defaultMessage(res.status), err?.fields ?? {});
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function defaultMessage(status: number): string {
  if (status === 404) return "We couldn't find that.";
  if (status === 403) return "You don't have access to that.";
  if (status === 429) return "That's a lot of requests — please wait a moment and try again.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return "Something went wrong.";
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", withQuery(path, query)),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: <T = void>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),
};

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Map server field errors onto react-hook-form fields; returns the non-field message, if any. */
export function applyServerErrors(err: unknown, setError: (name: never, e: { type: string; message: string }) => void, known: string[]): string {
  if (!(err instanceof ApiError)) return "Something went wrong.";
  let general = "";
  for (const [field, msgs] of Object.entries(err.fields)) {
    if (known.includes(field)) setError(field as never, { type: "server", message: msgs.join(" ") });
    else general = general || msgs.join(" ");
  }
  return Object.keys(err.fields).some((f) => known.includes(f)) ? general : general || err.message;
}
