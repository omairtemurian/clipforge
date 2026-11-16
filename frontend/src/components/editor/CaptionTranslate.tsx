import {
  ArrowUUpLeftIcon,
  CircleNotchIcon,
  TranslateIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { useRemoveTranslation, useTranslateCaptions } from "@/api/captions";
import { useSpeechLanguages } from "@/api/sources";
import type { CaptionTranslation } from "@/api/types";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";

interface CaptionTranslateProps {
  clipId: number;
  /** The clip's caption translation as edited (null: none). */
  translation: CaptionTranslation | null;
  /** Keep the translation the API saved in the edits too. */
  onChange: (translation: CaptionTranslation | null) => void;
}

/**
 * "Translate": the AI translates the saved clip's captions into a chosen
 * language (each line keeps its times), which the captions then show, right
 * to left for Persian, Arabic and Hebrew; "Show the original" goes back to
 * the transcript's words.
 */
export function CaptionTranslate({
  clipId,
  translation,
  onChange,
}: CaptionTranslateProps) {
  const languages = useSpeechLanguages();
  const translate = useTranslateCaptions(clipId);
  const remove = useRemoveTranslation(clipId);
  const [language, setLanguage] = useState("es");
  const name = (code: string) =>
    languages.data?.find((item) => item.code === code)?.name ?? code;
  const busy = translate.isPending || remove.isPending;

  return (
    <div className="flex flex-col gap-3">
      {translation && (
        <p className="text-body">
          Captions in {name(translation.language)} · {translation.cues.length}{" "}
          lines
        </p>
      )}
      <div className="flex items-center gap-2">
        <NativeSelect
          block
          aria-label="Translation language"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
        >
          {(languages.data ?? [{ code: language, name: name(language) }]).map(
            (item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ),
          )}
        </NativeSelect>
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={() =>
            translate.mutate(language, {
              onSuccess: (clip) => onChange(clip.caption_style.translation),
            })
          }
        >
          {translate.isPending ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <TranslateIcon aria-hidden />
          )}
          Translate
        </Button>
      </div>
      {translation && (
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() =>
            remove.mutate(undefined, { onSuccess: () => onChange(null) })
          }
        >
          <ArrowUUpLeftIcon aria-hidden />
          Show the original
        </Button>
      )}
      <p className="text-caption text-muted-foreground">
        Translates the saved clip&apos;s words.
      </p>
    </div>
  );
}
