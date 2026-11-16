import {
  CheckCircleIcon,
  InfoIcon,
  WarningCircleIcon,
  XIcon,
} from "@phosphor-icons/react";
import { dismissToast, useToasts, type ToastKind } from "@/lib/toast";

const ICONS = {
  error: <WarningCircleIcon className="size-4 text-destructive" />,
  success: <CheckCircleIcon className="size-4 text-chart-2" />,
  info: <InfoIcon className="size-4 text-primary-ink" />,
} satisfies Record<ToastKind, React.ReactNode>;

/** Stack of toasts in the bottom-right corner; errors are announced at once. */
export function Toaster() {
  const toasts = useToasts();

  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map(({ id, kind, message }) => (
        <div
          key={id}
          role={kind === "error" ? "alert" : "status"}
          className="pointer-events-auto flex items-start gap-3 rounded-lg border border-border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-popover"
        >
          <span className="mt-0.5">{ICONS[kind]}</span>
          <p className="flex-1 leading-5">{message}</p>
          <button
            type="button"
            aria-label="Dismiss"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => dismissToast(id)}
          >
            <XIcon className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
