import { ApiError, apiFetch } from "@/api/client";
import type { UploadSession } from "@/api/types";
import { toast } from "@/lib/toast";

/** Bytes per chunk: small enough to resend cheaply after a dropped connection. */
export const CHUNK_BYTES = 8 * 1024 * 1024;
const RESUME_PREFIX = "clipforge.upload:";

export interface ChunkedUploadOptions {
  /** Called after each stored chunk with the bytes on the server. */
  onProgress?: (sent: number, total: number) => void;
  chunkBytes?: number;
  /** Failed attempts in a row before giving up. */
  attempts?: number;
  /** Wait before retrying, multiplied by the attempt number. */
  retryDelayMs?: number;
}

/** The localStorage key that remembers the session of a file. */
function resumeKey(file: File): string {
  return `${RESUME_PREFIX}${file.name}:${file.size}:${file.lastModified}`;
}

/** Forget the session of a file once it became a project. */
export function forgetUpload(file: File): void {
  localStorage.removeItem(resumeKey(file));
}

/** The hex SHA-256 of a chunk (sent as X-Chunk-SHA256). */
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

/**
 * The session to continue for file: the one remembered from an earlier try
 * if the server still has it, else a new one (POST /uploads).
 */
async function openSession(file: File): Promise<UploadSession> {
  const remembered = localStorage.getItem(resumeKey(file));
  if (remembered) {
    try {
      const session = await apiFetch<UploadSession>(`/uploads/${remembered}`, {
        silent: true,
      });
      if (session.size === file.size) return session;
    } catch {
      // Gone (finished, cancelled or another data folder): start over.
    }
  }
  const session = await apiFetch<UploadSession>("/uploads", {
    method: "POST",
    json: { filename: file.name, size: file.size },
  });
  localStorage.setItem(resumeKey(file), session.id);
  return session;
}

/** Whether a failed chunk is worth resending after asking for the offset. */
function retryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return (
    error.status === 0 ||
    error.status >= 500 ||
    error.code === "offset_mismatch" ||
    error.code === "checksum_mismatch"
  );
}

async function sendChunk(
  session: UploadSession,
  file: File,
  offset: number,
  chunkBytes: number,
): Promise<UploadSession> {
  const data = await file.slice(offset, offset + chunkBytes).arrayBuffer();
  return apiFetch<UploadSession>(`/uploads/${session.id}?offset=${offset}`, {
    method: "PATCH",
    body: data,
    silent: true,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Chunk-SHA256": await sha256Hex(data),
    },
  });
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Send file to the server in chunks and return the upload id, ready for
 * POST /uploads/{id}/complete.
 *
 * A file uploaded before (same name, size, date) resumes from the offset the
 * server reports. A dropped connection, server error or offset/checksum
 * mismatch re-reads the offset and resends from there, up to `attempts`
 * failures in a row; the last error is then thrown (and shown as a toast).
 */
export async function uploadInChunks(
  file: File,
  options: ChunkedUploadOptions = {},
): Promise<string> {
  const {
    onProgress,
    chunkBytes = CHUNK_BYTES,
    attempts = 5,
    retryDelayMs = 1000,
  } = options;
  let session = await openSession(file);
  onProgress?.(session.offset, file.size);
  let failures = 0;
  while (session.offset < file.size) {
    try {
      session = await sendChunk(session, file, session.offset, chunkBytes);
      failures = 0;
      onProgress?.(session.offset, file.size);
    } catch (error) {
      failures += 1;
      if (!retryable(error) || failures >= attempts) {
        throw report(error);
      }
      await sleep(retryDelayMs * failures);
      session = await apiFetch<UploadSession>(`/uploads/${session.id}`, {
        silent: true,
      }).catch(() => session);
    }
  }
  return session.id;
}

/** Show a chunk's final error as a toast (chunks are sent silently). */
function report(error: unknown): unknown {
  if (error instanceof ApiError) toast.error(error.message);
  return error;
}
