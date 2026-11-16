import { toast } from "@/lib/toast";

export const API_BASE = "/api";

/** An error answer of the API: {error, message} (SPEC 7) plus the HTTP status. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export interface ApiOptions extends Omit<RequestInit, "body"> {
  /** Sent as a JSON body. */
  json?: unknown;
  /** Sent as is (FormData for uploads). */
  body?: BodyInit;
  /** Do not show the error as a toast; the caller reports it itself. */
  silent?: boolean;
}

/** The URL of an API path, e.g. apiUrl("/clips/3/video") -> "/api/clips/3/video". */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function errorFrom(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${response.status} ${response.statusText})`;
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object") {
      const { error, message: text } = body as Record<string, unknown>;
      if (typeof error === "string") code = error;
      if (typeof text === "string" && text) message = text;
    }
  } catch {
    // The body is not JSON (e.g. a proxy error page): keep the status line.
  }
  return new ApiError(response.status, code, message);
}

/**
 * Call the API and return the parsed JSON (undefined for 204).
 *
 * Any failure throws an ApiError carrying the server's message, and is shown
 * as an error toast unless `silent` is set.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { json, silent = false, headers, body, ...init } = options;
  const requestHeaders = new Headers(headers);
  let requestBody = body;
  if (json !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
    requestBody = JSON.stringify(json);
  }

  let failure: ApiError;
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: requestHeaders,
      body: requestBody,
    });
    if (response.ok) {
      return response.status === 204
        ? (undefined as T)
        : ((await response.json()) as T);
    }
    failure = await errorFrom(response);
  } catch (cause) {
    failure =
      cause instanceof ApiError
        ? cause
        : new ApiError(
            0,
            "network_error",
            "Cannot reach the ClipForge server. Is it running?",
          );
  }
  if (!silent) toast.error(failure.message);
  throw failure;
}
