import type { ClipTransitions, Transition } from "@/api/types";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { PanelGroup } from "@/components/ui/panel";
import { useGesture } from "@/hooks/useGesture";
import {
  TRANSITION_KINDS,
  TRANSITION_MAX_S,
  TRANSITION_MIN_S,
  pickTransition,
  sectionTransition,
  withAllSections,
  withSectionTransition,
  type TransitionKind,
} from "@/lib/overlays";

export interface TransitionPickerProps {
  transitions: ClipTransitions;
  /** How many sections the clip plays (cuts between them: one fewer). */
  sectionCount: number;
  /** New transitions; changes of one gesture (a slider drag) undo at once. */
  onChange: (transitions: ClipTransitions, gesture?: number) => void;
}

interface CutTransitionProps {
  label: string;
  value: Transition | null;
  onChange: (value: Transition | null, dragged?: boolean) => void;
  onStart: () => void;
}

/** A transition at a cut: its kind ("None": a hard cut) and length. */
function CutTransition({
  label,
  value,
  onChange,
  onStart,
}: CutTransitionProps) {
  return (
    <div className="flex flex-col gap-3">
      <Field label={label}>
        <NativeSelect
          block
          aria-label={label}
          value={value?.kind ?? "none"}
          onChange={(event) =>
            onChange(
              pickTransition(
                event.target.value as TransitionKind | "none",
                value,
              ),
            )
          }
        >
          <option value="none">None (hard cut)</option>
          {TRANSITION_KINDS.map(({ value: kind, label: name }) => (
            <option key={kind} value={kind}>
              {name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {value && (
        <PanelSlider
          label={`${label} length`}
          display={`${value.duration.toFixed(1)} s`}
          min={TRANSITION_MIN_S}
          max={TRANSITION_MAX_S}
          step={0.1}
          value={value.duration}
          onChange={(duration) => onChange({ ...value, duration }, true)}
          onStart={onStart}
        />
      )}
    </div>
  );
}

/**
 * The editor's Transitions panel (SPEC-v2 3.5): the transition at every
 * jump cut (where the clip's cut ranges and auto cut remove a part of a
 * section) and the transition at each cut between two sections in play
 * order: crossfade, zoom punch, whip or slide over 0.1-1 s, or none (a
 * hard cut). "Use the first for all" copies the first section cut's transition to
 * the others. The render draws them (pipeline/transitions).
 */
export function TransitionPicker({
  transitions,
  sectionCount,
  onChange,
}: TransitionPickerProps) {
  const gesture = useGesture();
  const cuts = Math.max(0, sectionCount - 1);
  const step = (dragged?: boolean) => (dragged ? gesture.current() : undefined);
  const first = sectionTransition(transitions, 0);

  return (
    <div className="flex flex-col gap-5">
      <PanelGroup title="Jump cuts">
        <CutTransition
          label="At jump cuts"
          value={transitions.auto}
          onChange={(auto, dragged) =>
            onChange({ ...transitions, auto }, step(dragged))
          }
          onStart={gesture.begin}
        />
      </PanelGroup>
      <PanelGroup title="Between sections">
        {cuts === 0 ? (
          <p className="text-caption text-muted-foreground">
            The clip plays one section. Add or split sections in the Sections
            panel to set a transition between them.
          </p>
        ) : (
          <>
            <ol aria-label="Section cuts" className="flex flex-col gap-5">
              {Array.from({ length: cuts }, (_, index) => (
                <li key={index}>
                  <CutTransition
                    label={`Section ${index + 1} to ${index + 2}`}
                    value={sectionTransition(transitions, index)}
                    onChange={(value, dragged) =>
                      onChange(
                        withSectionTransition(transitions, index, value),
                        step(dragged),
                      )
                    }
                    onStart={gesture.begin}
                  />
                </li>
              ))}
            </ol>
            {cuts > 1 && (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  onChange(withAllSections(transitions, sectionCount, first))
                }
              >
                Use the first for all
              </Button>
            )}
          </>
        )}
      </PanelGroup>
    </div>
  );
}
