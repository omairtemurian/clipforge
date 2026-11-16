/** Desktop alerts through the browser's Notification API. */

/** Whether this browser can show desktop alerts. */
export function desktopAlertsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

/** Whether the owner allowed desktop alerts. */
export function desktopAlertsAllowed(): boolean {
  return desktopAlertsSupported() && Notification.permission === "granted";
}

/** Ask for the permission; resolves to whether it was granted. */
export async function requestDesktopAlerts(): Promise<boolean> {
  if (!desktopAlertsSupported()) return false;
  return (await Notification.requestPermission()) === "granted";
}

/** Show a desktop alert if allowed (else nothing). */
export function showDesktopAlert(title: string, body: string): void {
  if (desktopAlertsAllowed()) new Notification(title, { body });
}
