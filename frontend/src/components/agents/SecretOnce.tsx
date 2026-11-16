import { KeyIcon } from "@phosphor-icons/react";
import { CopyButton } from "./CopyButton";

/** A secret just made (an API key, a webhook secret), shown this one time
 * with a copy button. */
export function SecretOnce({
  label,
  secret,
  onDone,
}: {
  label: string;
  secret: string;
  onDone: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-col gap-3 rounded-xl border border-warning/40 bg-warning/10 p-4"
    >
      <p className="flex items-center gap-2 text-body font-medium">
        <KeyIcon aria-hidden className="size-4 text-warning" />
        {label}: copy it now. It is shown only once.
      </p>
      <div className="flex items-center gap-2">
        <code
          aria-label={label}
          className="min-w-0 flex-1 rounded-md bg-background px-3 py-2 font-mono text-caption break-all select-all"
        >
          {secret}
        </code>
        <CopyButton text={secret} label={`Copy ${label}`} />
      </div>
      <button
        type="button"
        onClick={onDone}
        className="self-start text-caption text-muted-foreground underline-offset-4 hover:underline"
      >
        I saved it, hide it
      </button>
    </div>
  );
}
