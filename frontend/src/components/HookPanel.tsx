import { EraserIcon, LightningIcon, SparkleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useHookOps, useHookTemplates, type HookOp } from "@/api/clipGraphics";
import type { Clip, HookTemplateInfo } from "@/api/types";
import { HeadlineGroup } from "@/components/HeadlineGroup";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { PanelGroup } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { choiceClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import {
  HOOK_SECONDS_MAX,
  HOOK_SECONDS_MIN,
  HOOK_SOURCES,
  HOOK_TEXT_MAX,
  type HookSource,
} from "@/lib/viralHooks";

interface HookPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
}

interface TemplateListProps {
  templates: HookTemplateInfo[];
  chosen: string;
  disabled: boolean;
  onChoose: (name: string) => void;
}

/** The hook templates to pick from, with what each one does. */
function TemplateList({
  templates,
  chosen,
  disabled,
  onChoose,
}: TemplateListProps) {
  return (
    <ul aria-label="Hook templates" className="flex flex-col gap-2">
      {templates.map((template) => (
        <li key={template.name}>
          <button
            type="button"
            aria-pressed={template.name === chosen}
            disabled={disabled}
            onClick={() => onChoose(template.name)}
            className={cn(
              choiceClass(template.name === chosen),
              "flex w-full cursor-pointer flex-col items-start gap-0.5 text-left disabled:cursor-not-allowed disabled:opacity-60",
            )}
          >
            <span className="text-body font-medium">{template.label}</span>
            <span className="text-caption text-muted-foreground">
              {template.description}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

const seconds = (value: number) => `${value.toFixed(1)} s`;

/**
 * The editor's Hooks panel (SPEC-v2 3.5): the viral hook over the first
 * seconds of the clip's render. Pick a template, where its text comes
 * from (the opening words of the captions, a line the AI writes, or your
 * own) and how long it lasts to add it; later change its template, text
 * or length, write its text again, or remove it. Below it the headline.
 * The edits act on the saved clip, so they wait for unsaved changes
 * (autosave saves them); the clip an edit answers replaces the editor's.
 * The video changes when the clip is rendered again.
 */
export function HookPanel({ clip, edits, busy }: HookPanelProps) {
  const templates = useHookTemplates();
  const ops = useHookOps(clip.id);
  const hook = clip.hook;
  const [template, setTemplate] = useState<string | null>(null);
  const [source, setSource] = useState<HookSource>("captions");
  const [own, setOwn] = useState("");
  const [typed, setTyped] = useState<string | null>(null);
  const [length, setLength] = useState<number | null>(null);
  const waiting = edits.dirty || busy;
  const locked = waiting || ops.isPending;

  const list = templates.data ?? [];
  const chosen = hook?.template ?? template ?? list[0]?.name ?? "";
  const info = list.find((item) => item.name === chosen);
  const duration = length ?? hook?.duration ?? info?.duration ?? 2.5;
  const text = typed ?? hook?.text ?? "";

  const run = async (op: HookOp) => {
    try {
      edits.reset(await ops.mutateAsync(op));
      setTyped(null);
      setLength(null);
    } catch {
      // apiFetch has shown the error
    }
  };
  const apply = (from: HookSource, given: string | null) =>
    run({
      type: "apply",
      body: {
        template: chosen,
        source: from,
        text: from === "text" ? given : null,
        duration,
      },
    });

  if (templates.isPending) {
    return <Skeleton className="h-40 rounded-xl" />;
  }
  if (list.length === 0) {
    return (
      <EmptyState
        icon={LightningIcon}
        title="No hook templates"
        className="py-8"
      >
        The hook templates could not be loaded.
      </EmptyState>
    );
  }

  return (
    <>
      {waiting && (
        <p role="status" className="text-caption text-muted-foreground">
          Edits wait until your changes are saved.
        </p>
      )}
      <PanelGroup title="Hook">
        <TemplateList
          templates={list}
          chosen={chosen}
          disabled={locked}
          onChoose={(name) =>
            hook
              ? void run({ type: "edit", body: { template: name } })
              : setTemplate(name)
          }
        />
        <PanelSlider
          label="Hook length"
          display={seconds(duration)}
          min={HOOK_SECONDS_MIN}
          max={HOOK_SECONDS_MAX}
          step={0.1}
          value={duration}
          disabled={locked}
          onChange={setLength}
          onCommit={(value) =>
            hook && void run({ type: "edit", body: { duration: value } })
          }
        />
        {hook ? (
          <>
            <Field label="Hook text" htmlFor="hook-text">
              <input
                id="hook-text"
                value={text}
                maxLength={HOOK_TEXT_MAX}
                onChange={(event) => setTyped(event.target.value)}
                className={cn(INPUT, "h-9")}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={
                  locked || text.trim() === "" || text.trim() === hook.text
                }
                onClick={() =>
                  void run({ type: "edit", body: { text: text.trim() } })
                }
              >
                Save text
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={locked}
                onClick={() => void apply("captions", null)}
              >
                Use the captions
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={locked}
                onClick={() => void apply("theme", null)}
              >
                <SparkleIcon />
                Write a new line
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={locked}
                onClick={() => void run({ type: "remove" })}
              >
                <EraserIcon />
                Remove hook
              </Button>
            </div>
          </>
        ) : (
          <>
            <Field label="Hook text from">
              <NativeSelect
                block
                aria-label="Hook text from"
                value={source}
                onChange={(event) =>
                  setSource(event.target.value as HookSource)
                }
              >
                {HOOK_SOURCES.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {source === "text" && (
              <Field label="Your hook text" htmlFor="hook-own-text">
                <input
                  id="hook-own-text"
                  value={own}
                  maxLength={HOOK_TEXT_MAX}
                  onChange={(event) => setOwn(event.target.value)}
                  className={cn(INPUT, "h-9")}
                />
              </Field>
            )}
            <Button
              disabled={locked || (source === "text" && own.trim() === "")}
              onClick={() => void apply(source, own.trim())}
            >
              <LightningIcon />
              Add hook
            </Button>
          </>
        )}
        {ops.isPending && (
          <p role="status" className="text-caption text-muted-foreground">
            Working…
          </p>
        )}
        <p className="text-caption text-muted-foreground">
          Render the clip again to see the hook in the video.
        </p>
      </PanelGroup>
      <HeadlineGroup clip={clip} edits={edits} locked={locked} />
    </>
  );
}
