import { useState } from "react";
import type { EdlItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { INPUT, NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";
import { KIND_LABELS } from "./laneMath";
import {
  draftChanged,
  draftOf,
  paramFields,
  paramsOf,
  type ParamDraft,
  type ParamField,
} from "./paramFields";

const LABEL = "text-body font-medium";

/** The input of one param. */
function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: ParamField;
  value: string | boolean;
  disabled: boolean;
  onChange: (value: string | boolean) => void;
}) {
  const id = `inspector-${field.key}`;
  if (field.type === "boolean") {
    return (
      <label htmlFor={id} className="flex items-center gap-2 text-body">
        <input
          id={id}
          type="checkbox"
          checked={value === true}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="size-4 accent-primary"
        />
        {field.key}
      </label>
    );
  }
  const text = String(value);
  const choices = field.options.includes(text)
    ? field.options
    : [text, ...field.options];
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={LABEL}>
        {field.key}
      </label>
      {field.type === "select" ? (
        <NativeSelect
          id={id}
          block
          value={text}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {choices.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </NativeSelect>
      ) : (
        <input
          id={id}
          type={field.type === "number" ? "number" : "text"}
          step={field.type === "number" ? "any" : undefined}
          value={text}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          className={cn(INPUT, "h-9")}
        />
      )}
    </div>
  );
}

/** The form of item; remounted per item and per stored params. */
function ParamsForm({
  item,
  fields,
  disabled,
  onApply,
}: {
  item: EdlItem;
  fields: ParamField[];
  disabled: boolean;
  onApply: (item: EdlItem) => void;
}) {
  const [draft, setDraft] = useState<ParamDraft>(() => draftOf(item));
  const [error, setError] = useState<string | null>(null);
  const changed = draftChanged(item, draft);
  const submit = () => {
    const next = paramsOf(item, draft);
    if ("error" in next) {
      setError(next.error);
      return;
    }
    setError(null);
    onApply({ ...item, params: next.params });
  };

  return (
    <form
      aria-label="Item parameters"
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {fields.length === 0 && (
        <p className="text-body text-muted-foreground">
          This item has no parameters.
        </p>
      )}
      {fields.map((field) => (
        <FieldInput
          key={field.key}
          field={field}
          value={draft[field.key]}
          disabled={disabled}
          onChange={(value) => {
            setError(null);
            setDraft({ ...draft, [field.key]: value });
          }}
        />
      ))}
      {error && (
        <p role="alert" className="text-body text-destructive">
          {error}
        </p>
      )}
      {fields.length > 0 && (
        <Button type="submit" size="sm" disabled={disabled || !changed}>
          Apply
        </Button>
      )}
    </form>
  );
}

/**
 * The inspector of the selected EDL item (SPEC-v3 3.8): a field per param
 * (a select for the choices, a number, a checkbox or text). Apply hands
 * the item with its new params to onApply, which stores them as the next
 * plan version; the server checks the ranges and answers with its reasons.
 */
export function Inspector({
  item,
  disabled,
  onApply,
}: {
  item: EdlItem | undefined;
  disabled: boolean;
  onApply: (item: EdlItem) => void;
}) {
  return (
    <section aria-label="Inspector" className="flex flex-col gap-3">
      <h3 className="text-body font-semibold">
        {item ? `${KIND_LABELS[item.kind]} parameters` : "Inspector"}
      </h3>
      {item ? (
        <ParamsForm
          key={`${item.id}:${JSON.stringify(item.params)}`}
          item={item}
          fields={paramFields(item)}
          disabled={disabled}
          onApply={onApply}
        />
      ) : (
        <p className="text-body text-muted-foreground">
          Select an item to change its parameters.
        </p>
      )}
    </section>
  );
}
