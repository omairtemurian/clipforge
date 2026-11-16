import { useState } from "react";
import { FloppyDiskIcon } from "@phosphor-icons/react";
import { useSaveDefault } from "@/api/presets";
import { useProcessingDefaults } from "@/api/sources";
import { LanguageField } from "@/components/settings/LanguageField";
import { Button } from "@/components/ui/button";
import { Section } from "./Section";

/** The speech language that new projects start with. The rest of the
 * defaults (clip length, captions, layout) are set in a project's settings
 * panel with "Save as default". */
export function NewProjectDefaults() {
  const defaults = useProcessingDefaults();
  const save = useSaveDefault();
  const [chosen, setChosen] = useState<string | null | undefined>(undefined);
  const saved = defaults.data?.language ?? null;
  const language = chosen === undefined ? saved : chosen;
  const dirty = language !== saved;

  return (
    <Section
      title="Defaults for new projects"
      description="What a new project starts with. Change the other defaults in the settings panel of a project and press Save as default."
    >
      {defaults.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the defaults.
        </p>
      )}
      {defaults.data && (
        <LanguageField
          settings={{ ...defaults.data, language }}
          allowSubtitles={false}
          onChange={(patch) => setChosen(patch.language ?? null)}
        />
      )}
      <div>
        <Button
          type="button"
          disabled={!defaults.data || !dirty || save.isPending}
          onClick={() =>
            defaults.data &&
            save.mutate(
              { ...defaults.data, language, subtitles_id: null },
              { onSuccess: () => setChosen(undefined) },
            )
          }
        >
          <FloppyDiskIcon aria-hidden />
          {save.isPending ? "Saving…" : "Save default language"}
        </Button>
      </div>
    </Section>
  );
}
