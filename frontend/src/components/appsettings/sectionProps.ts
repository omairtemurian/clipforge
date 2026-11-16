import type {
  KeyDraft,
  KeyField,
  SettingsDraft,
  TextField,
} from "@/lib/settingsForm";

/** What every section of the Settings page gets. */
export interface SectionProps {
  draft: SettingsDraft;
  /** Problems to show by field (after the first Save). */
  problems: Partial<Record<TextField, string>>;
  onText: (field: TextField, value: string) => void;
  onKey: (field: KeyField, key: KeyDraft) => void;
}
