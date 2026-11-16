import { Link } from "react-router-dom";
import { TextSetting } from "./TextSetting";
import { Section } from "./Section";
import type { SectionProps } from "./sectionProps";

interface StoragePathsSectionProps extends SectionProps {
  dataDir: string;
}

/** Where ClipForge keeps its files: the models folder (editable) and the
 * data folder (projects, clips, exports; set with DATA_DIR). */
export function StoragePathsSection({
  draft,
  problems,
  onText,
  dataDir,
}: StoragePathsSectionProps) {
  return (
    <Section
      title="Storage paths"
      description="Where ClipForge keeps its files."
    >
      <TextSetting
        label="Models folder"
        hint="Where the downloaded models are kept."
        value={draft.text.models_dir}
        error={problems.models_dir}
        onChange={(value) => onText("models_dir", value)}
      />
      <p className="text-caption text-muted-foreground">
        Data folder: <code className="text-foreground">{dataDir}</code> (change
        it with the DATA_DIR setting and restart). See the{" "}
        <Link
          to="/settings/storage"
          className="text-primary-ink underline underline-offset-2"
        >
          Storage tab
        </Link>{" "}
        for disk use and clean-up.
      </p>
    </Section>
  );
}
