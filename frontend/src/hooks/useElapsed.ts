import { useEffect, useState } from "react";

/**
 * The seconds since start (a Date.now() value), counted every second while
 * running; once running is false the last count stays.
 */
export function useElapsed(start: number, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return Math.max(0, (now - start) / 1000);
}
