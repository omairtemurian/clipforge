import { useState } from "react";
import { FloppyDiskIcon, TrashIcon } from "@phosphor-icons/react";
import { apiUrl } from "@/api/client";
import {
  useBrandFonts,
  useDeleteBrandTemplate,
  useSaveBrandTemplate,
} from "@/api/templates";
import type { BrandTemplate } from "@/api/types";
import { ColorField } from "@/components/editor/ColorField";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import {
  brandFormData,
  draftOf,
  fileName,
  LOGO_TYPES,
  validateBrand,
  VIDEO_SUFFIXES,
  type BrandDraft,
  type LogoPosition,
} from "@/lib/brandForm";
import { cn } from "@/lib/utils";
import { BrandPreview } from "./BrandPreview";
import { FileField } from "./FileField";
import { cardClass } from "@/lib/surfaces";

const POSITIONS: { value: LogoPosition; label: string }[] = [
  { value: "tl", label: "Top left" },
  { value: "tr", label: "Top right" },
  { value: "bl", label: "Bottom left" },
  { value: "br", label: "Bottom right" },
];

interface BrandFormProps {
  /** The template to change; absent for a new one. */
  template?: BrandTemplate;
  /** Changes whenever the saved logo may have changed (cache buster). */
  logoVersion: number;
  onSaved: (saved: BrandTemplate) => void;
  onDeleted: () => void;
}

/**
 * The create / edit form of a brand template next to its live preview frame.
 * The parent keys it by template id, so its draft starts fresh per template.
 */
export function BrandForm({
  template,
  logoVersion,
  onSaved,
  onDeleted,
}: BrandFormProps) {
  const [draft, setDraft] = useState<BrandDraft>(() => draftOf(template));
  const [submitted, setSubmitted] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const fonts = useBrandFonts().data ?? [];
  const save = useSaveBrandTemplate(onSaved);
  const remove = useDeleteBrandTemplate(onDeleted);

  const problems = validateBrand(draft, template !== undefined, fonts);
  const shown = submitted ? problems : {};
  const set = (change: Partial<BrandDraft>) =>
    setDraft((current) => ({ ...current, ...change }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(problems).length > 0) return;
    save.mutate({ id: template?.id ?? null, form: brandFormData(draft) });
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={template ? `Edit ${template.name}` : "New brand template"}
      className={cn(cardClass(), "flex flex-col gap-6 p-6 lg:flex-row")}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-5">
        <h2 className="text-section">
          {template ? "Edit template" : "New template"}
        </h2>
        <Field label="Name" htmlFor="brand-name">
          <input
            id="brand-name"
            value={draft.name}
            maxLength={60}
            aria-invalid={shown.name !== undefined}
            onChange={(event) => set({ name: event.target.value })}
            className={cn(INPUT, "h-9")}
          />
          {shown.name && (
            <p role="alert" className="text-caption text-destructive">
              {shown.name}
            </p>
          )}
        </Field>
        <FileField
          label="Logo"
          accept={LOGO_TYPES.join(",")}
          file={draft.logo}
          savedName={template ? fileName(template.logo_path) : null}
          error={shown.logo}
          onPick={(logo) => set({ logo })}
        />
        <Field label="Logo position">
          <ChoiceChips
            label="Logo position"
            options={POSITIONS}
            value={draft.position}
            onChange={(position) => set({ position })}
          />
        </Field>
        <PanelSlider
          label="Logo opacity"
          display={`${Math.round(draft.opacity * 100)}%`}
          min={0.1}
          max={1}
          step={0.05}
          value={draft.opacity}
          onChange={(opacity) => set({ opacity })}
        />
        <div className="grid grid-cols-[1fr_8rem] items-start gap-4">
          <Field label="Font" htmlFor="brand-font">
            <NativeSelect
              id="brand-font"
              value={draft.font}
              onChange={(event) => set({ font: event.target.value })}
              block
            >
              {!fonts.includes(draft.font) && (
                <option value={draft.font}>{draft.font}</option>
              )}
              {fonts.map((font) => (
                <option key={font} value={font}>
                  {font}
                </option>
              ))}
            </NativeSelect>
            {shown.font && (
              <p role="alert" className="text-caption text-destructive">
                {shown.font}
              </p>
            )}
          </Field>
          <ColorField
            label="Primary color"
            value={draft.color}
            onChange={(color) => set({ color })}
          />
        </div>
        <FileField
          label="Intro video"
          accept={VIDEO_SUFFIXES.join(",")}
          file={draft.intro}
          savedName={template?.intro_path && fileName(template.intro_path)}
          removed={draft.removeIntro}
          error={shown.intro}
          onPick={(intro) => set({ intro })}
          onRemove={(removeIntro) => set({ removeIntro })}
        />
        <FileField
          label="Outro video"
          accept={VIDEO_SUFFIXES.join(",")}
          file={draft.outro}
          savedName={template?.outro_path && fileName(template.outro_path)}
          removed={draft.removeOutro}
          error={shown.outro}
          onPick={(outro) => set({ outro })}
          onRemove={(removeOutro) => set({ removeOutro })}
        />
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={save.isPending}>
            <FloppyDiskIcon aria-hidden />
            {save.isPending
              ? "Saving…"
              : template
                ? "Save changes"
                : "Create template"}
          </Button>
          {template &&
            (confirmingDelete ? (
              <>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(template.id)}
                >
                  Confirm delete
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setConfirmingDelete(false)}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setConfirmingDelete(true)}
              >
                <TrashIcon aria-hidden />
                Delete
              </Button>
            ))}
        </div>
      </div>
      <BrandPreview
        name={draft.name}
        position={draft.position}
        opacity={draft.opacity}
        color={draft.color}
        font={draft.font}
        logoFile={draft.logo}
        savedLogoUrl={
          template
            ? apiUrl(`/brand-templates/${template.id}/logo?v=${logoVersion}`)
            : null
        }
      />
    </form>
  );
}
