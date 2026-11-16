import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowCounterClockwiseIcon,
  BookOpenTextIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { clipQuery } from "@/api/clips";
import { useCaptionTemplates } from "@/api/templates";
import type { CaptionStyle, Clip, Word } from "@/api/types";
import { CaptionCensor } from "@/components/editor/CaptionCensor";
import { CaptionPreview } from "@/components/editor/CaptionPreview";
import {
  CaptionStyleFields,
  type SetStyle,
} from "@/components/editor/CaptionStyleFields";
import { CaptionTranslate } from "@/components/editor/CaptionTranslate";
import { CaptionWordTexts } from "@/components/editor/CaptionWordTexts";
import { SpeakerColors } from "@/components/editor/SpeakerColors";
import { TemplateGallery } from "@/components/editor/TemplateGallery";
import { VocabularyDialog } from "@/components/editor/VocabularyDialog";
import { CaptionCarousel } from "@/components/settings/CaptionCarousel";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useGesture } from "@/hooks/useGesture";
import {
  resetStyle,
  effectiveTemplate,
  isStyled,
  withStyleField,
} from "@/lib/clipLook";
import { speakersOf } from "@/lib/wordMarks";
import { captionedWords } from "@/lib/wordTexts";

interface CaptionsPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** The clip's transcript words (with context), once loaded. */
  words: Word[] | undefined;
}

/**
 * The editor's Captions tab: the caption template (a row, or every one in
 * "All templates") with a live preview, the style fields that replace the
 * template's, a color per speaker, each caption word's text and popover
 * (highlight, emoji, censor, color), the translation of the captions,
 * censoring, and the brand vocabulary. Choosing another template drops the
 * style but keeps the clip's speaker colors, word marks, translation and
 * censor.
 */
export function CaptionsPanel({ clip, edits, words }: CaptionsPanelProps) {
  const templates = useCaptionTemplates();
  const gesture = useGesture();
  const queryClient = useQueryClient();
  const [vocabulary, setVocabulary] = useState(false);
  const { look } = edits;
  const style = look.caption_style;
  const base = templates.data?.find(
    (info) => info.name === look.caption_template,
  )?.template;
  const shown = base && effectiveTemplate(base, style);
  const captioned = words && captionedWords(words, edits.range, edits.cuts);

  const setCaptionStyle = (next: Partial<CaptionStyle>, dragged = false) =>
    edits.setLook(
      { caption_style: { ...style, ...next } },
      dragged ? gesture.current() : undefined,
    );
  const setStyle: SetStyle = (field, value, dragged = false) => {
    if (!base) return;
    edits.setLook(
      { caption_style: withStyleField(style, base, field, value) },
      dragged ? gesture.current() : undefined,
    );
  };
  const chooseTemplate = (name: string) =>
    edits.setLook({ caption_template: name, caption_style: resetStyle(style) });

  return (
    <>
      <PanelGroup title="Style" collapsible>
        <Field label="Template">
          <div className="relative pt-9">
            <CaptionCarousel
              templates={templates.data}
              value={look.caption_template}
              onChange={chooseTemplate}
            />
          </div>
          <TemplateGallery
            templates={templates.data}
            value={look.caption_template}
            onChange={chooseTemplate}
          />
        </Field>
        {shown && (
          <>
            <CaptionPreview
              name={look.caption_template}
              template={shown}
              style={style}
            />
            <CaptionStyleFields
              shown={shown}
              setStyle={setStyle}
              onStart={gesture.begin}
            />
            {isStyled(style) && (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  edits.setLook({ caption_style: resetStyle(style) })
                }
              >
                <ArrowCounterClockwiseIcon aria-hidden />
                Reset to the template
              </Button>
            )}
          </>
        )}
      </PanelGroup>
      <PanelGroup title="Caption words" collapsible>
        <Field label="Words">
          {captioned && shown ? (
            <CaptionWordTexts
              words={captioned}
              overrides={look.caption_overrides}
              onChange={(caption_overrides) =>
                edits.setLook({ caption_overrides })
              }
              marks={style.word_marks}
              onMarks={(word_marks, dragged) =>
                setCaptionStyle({ word_marks }, dragged)
              }
              onMarkStart={gesture.begin}
              baseColor={shown.primary_color}
            />
          ) : (
            <p className="text-body text-muted-foreground">
              The words are loading.
            </p>
          )}
        </Field>
      </PanelGroup>
      <PanelGroup title="Speakers" collapsible defaultOpen={false}>
        {captioned && shown && (
          <SpeakerColors
            speakers={speakersOf(captioned)}
            colors={style.speaker_colors}
            baseColor={shown.primary_color}
            onChange={(speaker_colors, dragged) =>
              setCaptionStyle({ speaker_colors }, dragged)
            }
            onStart={gesture.begin}
          />
        )}
      </PanelGroup>
      <PanelGroup title="Translate" collapsible defaultOpen={false}>
        <CaptionTranslate
          clipId={clip.id}
          translation={style.translation}
          onChange={(translation) => setCaptionStyle({ translation })}
        />
      </PanelGroup>
      <PanelGroup title="Censor" collapsible defaultOpen={false}>
        <CaptionCensor
          value={style.censor}
          onChange={(censor) => setCaptionStyle({ censor })}
        />
      </PanelGroup>
      <PanelGroup title="Vocabulary" collapsible defaultOpen={false}>
        <p className="text-body text-muted-foreground">
          Teach transcription your brand&apos;s words and fix a word in every
          clip of this project.
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => setVocabulary(true)}
        >
          <BookOpenTextIcon aria-hidden />
          Brand vocabulary
        </Button>
      </PanelGroup>
      {vocabulary && (
        <VocabularyDialog
          projectId={clip.project_id}
          replaceBlocked={edits.dirty ? "Save the clip's changes first." : null}
          onReplaced={() =>
            void queryClient
              .fetchQuery(clipQuery(clip.id))
              .then((saved) => edits.reset(saved))
          }
          onClose={() => setVocabulary(false)}
        />
      )}
      <p className="text-caption text-muted-foreground">
        The preview shows these changes once the clip is saved.
      </p>
    </>
  );
}
