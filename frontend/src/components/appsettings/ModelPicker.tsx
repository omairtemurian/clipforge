import { useEffect, useState } from "react";
import { ArrowsCounterClockwiseIcon } from "@phosphor-icons/react";
import { useLlmModels } from "@/api/appSettings";
import type { SettingsView } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import { llmTestBody, type TextField } from "@/lib/settingsForm";
import { TextSetting } from "./TextSetting";
import type { SectionProps } from "./sectionProps";

const CUSTOM = "\u0000custom";

interface ModelPickerProps extends Omit<SectionProps, "onKey"> {
  saved: SettingsView;
  /** The setting that holds the model of the provider. */
  field: Extract<TextField, "llm_model" | "anthropic_model">;
  hint?: string;
}

/**
 * The model of the language model provider: a dropdown of the models that
 * the provider lists (loaded on open, and again with "Load models" after a
 * key or address was typed) and a "Custom…" choice for any other id. Until
 * a list arrives, or when it cannot be loaded, the model is a text field.
 */
export function ModelPicker({
  draft,
  saved,
  field,
  problems,
  onText,
  hint,
}: ModelPickerProps) {
  const lister = useLlmModels();
  const { mutate } = lister;
  const value = draft.text[field];
  const [custom, setCustom] = useState(false);
  const body = llmTestBody(draft, saved);
  const [opening] = useState(body);
  useEffect(() => {
    mutate(opening);
  }, [mutate, opening]);

  const listed = lister.data;
  const models = listed?.models ?? [];
  const isCustom = custom || !models.includes(value);
  const error = lister.isError
    ? "The models could not be loaded."
    : (listed?.error ?? undefined);
  const id = `${field}-picker`;

  return (
    <>
      {models.length > 0 ? (
        <>
          <Field label="Model" htmlFor={id}>
            <NativeSelect
              id={id}
              block
              value={isCustom ? CUSTOM : value}
              onChange={(event) => {
                const chosen = event.target.value;
                setCustom(chosen === CUSTOM);
                if (chosen !== CUSTOM) onText(field, chosen);
              }}
            >
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
              <option value={CUSTOM}>Custom…</option>
            </NativeSelect>
            {hint && (
              <p className="text-caption text-muted-foreground">{hint}</p>
            )}
          </Field>
          {isCustom && (
            <TextSetting
              label="Custom model"
              value={value}
              error={problems[field]}
              onChange={(next) => onText(field, next)}
            />
          )}
        </>
      ) : (
        <TextSetting
          label="Model"
          value={value}
          error={problems[field]}
          hint={hint}
          onChange={(next) => onText(field, next)}
        />
      )}
      <div className="flex flex-col gap-1">
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={lister.isPending}
            onClick={() => mutate(body)}
          >
            <ArrowsCounterClockwiseIcon aria-hidden />
            {lister.isPending ? "Loading models…" : "Load models"}
          </Button>
        </div>
        {!lister.isPending && (error || models.length > 0) && (
          <p
            role="status"
            className={
              error
                ? "text-caption text-destructive"
                : "text-caption text-muted-foreground"
            }
          >
            {error ?? `${models.length} models available.`}
          </p>
        )}
      </div>
    </>
  );
}
