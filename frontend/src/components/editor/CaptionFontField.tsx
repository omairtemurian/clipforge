import { CircleNotchIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { useRef } from "react";
import { useUploadFont } from "@/api/captions";
import { useBrandFonts } from "@/api/templates";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";

interface CaptionFontFieldProps {
  value: string;
  onChange: (font: string) => void;
  /** The select's accessible name. */
  ariaLabel?: string;
}

/**
 * The caption font: a select of the bundled and uploaded fonts (by the
 * names a caption style can use) and "Upload font", which adds a TTF or
 * OTF file to the library and chooses it. Text layers use it too.
 */
export function CaptionFontField({
  value,
  onChange,
  ariaLabel = "Caption font",
}: CaptionFontFieldProps) {
  const fonts = useBrandFonts();
  const upload = useUploadFont();
  const input = useRef<HTMLInputElement>(null);
  const names = fonts.data ?? [];
  const options = names.includes(value) ? names : [value, ...names];

  const add = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (font) => font.names[0] && onChange(font.names[0]),
      onSettled: () => {
        if (input.current) input.current.value = "";
      },
    });
  };

  return (
    <Field label="Font">
      <div className="flex items-center gap-2">
        <NativeSelect
          block
          aria-label={ariaLabel}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {options.map((name) => (
            <option key={name} value={name} style={{ fontFamily: name }}>
              {name}
            </option>
          ))}
        </NativeSelect>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Upload font"
          title="Upload a TTF or OTF font"
          disabled={upload.isPending}
          onClick={() => input.current?.click()}
        >
          {upload.isPending ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <UploadSimpleIcon aria-hidden />
          )}
        </Button>
        <input
          ref={input}
          type="file"
          accept=".ttf,.otf,font/ttf,font/otf"
          aria-label="Font file"
          className="hidden"
          onChange={(event) => add(event.target.files?.[0])}
        />
      </div>
    </Field>
  );
}
