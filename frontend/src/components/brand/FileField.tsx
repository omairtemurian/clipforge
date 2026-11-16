import { useRef } from "react";
import { UploadSimpleIcon, XIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/settings/Field";

interface FileFieldProps {
  label: string;
  accept: string;
  /** The file picked now. */
  file: File | null;
  /** The name of the file saved with the template, if any. */
  savedName?: string | null;
  /** The saved file is to be dropped. */
  removed?: boolean;
  error?: string;
  onPick: (file: File | null) => void;
  /** Present for a saved file that can be dropped (optional videos). */
  onRemove?: (removed: boolean) => void;
}

/** A labelled file picker with the current file's name and a way to clear it. */
export function FileField({
  label,
  accept,
  file,
  savedName,
  removed = false,
  error,
  onPick,
  onRemove,
}: FileFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const shown = file ? file.name : removed ? null : (savedName ?? null);
  const clearable = file !== null || (shown !== null && onRemove !== undefined);

  function clear() {
    if (input.current) input.current.value = "";
    onPick(null);
    if (!file) onRemove?.(true);
  }

  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input
          ref={input}
          type="file"
          accept={accept}
          aria-label={label}
          aria-invalid={error !== undefined}
          className="sr-only"
          onChange={(event) => {
            onPick(event.target.files?.[0] ?? null);
            onRemove?.(false);
          }}
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => input.current?.click()}
        >
          <UploadSimpleIcon aria-hidden />
          {shown ? "Replace" : "Choose file"}
        </Button>
        <span className="min-w-0 flex-1 truncate text-body text-muted-foreground">
          {shown ?? "None"}
        </span>
        {clearable && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${label.toLowerCase()}`}
            onClick={clear}
          >
            <XIcon aria-hidden />
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-caption text-destructive">
          {error}
        </p>
      )}
    </Field>
  );
}
