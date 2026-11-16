import { useEffect, useRef, useState } from "react";
import { apiUrl } from "@/api/client";
import { logText, type JobEvent } from "@/lib/processingSteps";

export interface LogLine {
  /** Date.now() when the event arrived. */
  at: number;
  text: string;
}

export interface JobEvents {
  /** The latest event, or null until the first one arrives. */
  event: JobEvent | null;
  /** One line for each change of step or status seen since the page opened. */
  log: LogLine[];
}

const ENDED = ["done", "failed"];
const STATUSES = ["queued", "running", "done", "failed"];

function parseEvent(data: string): JobEvent | null {
  try {
    const value: unknown = JSON.parse(data);
    if (value === null || typeof value !== "object") return null;
    const { step, progress, status, message, overall_progress, eta_seconds } =
      value as Record<string, unknown>;
    if (
      typeof step !== "string" ||
      typeof progress !== "number" ||
      typeof message !== "string" ||
      typeof status !== "string" ||
      !STATUSES.includes(status)
    ) {
      return null;
    }
    return {
      step,
      progress,
      status: status as JobEvent["status"],
      message,
      overall_progress:
        typeof overall_progress === "number" ? overall_progress : undefined,
      eta_seconds: typeof eta_seconds === "number" ? eta_seconds : null,
    };
  } catch {
    return null;
  }
}

/**
 * Follow a job's progress with its server-sent events (GET /jobs/{id}/events).
 *
 * The server sends the current state first, so a page opened in the middle of
 * a job picks up where it is. The stream is closed once the job is done or
 * failed, then onEnd is called with that last event. A dropped connection is
 * reopened by the browser itself.
 */
export function useJobEvents(
  jobId: number | undefined,
  onEnd?: (event: JobEvent) => void,
): JobEvents {
  const [state, setState] = useState<{ jobId?: number } & JobEvents>({
    event: null,
    log: [],
  });
  const onEndRef = useRef(onEnd);
  useEffect(() => {
    onEndRef.current = onEnd;
  });

  useEffect(() => {
    if (jobId === undefined) return;

    const source = new EventSource(apiUrl(`/jobs/${jobId}/events`));
    source.onmessage = (message: MessageEvent<string>) => {
      const event = parseEvent(message.data);
      if (event === null) return;
      setState((previous) => {
        const own =
          previous.jobId === jobId ? previous : { event: null, log: [] };
        const last = own.event;
        const changed = last === null || logText(last) !== logText(event);
        const log = changed
          ? [...own.log, { at: Date.now(), text: logText(event) }]
          : own.log;
        return { jobId, event, log };
      });
      if (ENDED.includes(event.status)) {
        source.close();
        onEndRef.current?.(event);
      }
    };
    return () => source.close();
  }, [jobId]);

  return state.jobId === jobId ? state : { event: null, log: [] };
}
