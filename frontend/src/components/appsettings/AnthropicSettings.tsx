import type { SettingsView } from "@/api/types";
import { ModelPicker } from "./ModelPicker";
import { SecretSetting } from "./SecretSetting";
import { TextSetting } from "./TextSetting";
import type { SectionProps } from "./sectionProps";

interface AnthropicSettingsProps extends SectionProps {
  saved: SettingsView;
}

/** The Anthropic API provider: model (a dropdown of the key's models once
 * listed), base URL and API key. */
export function AnthropicSettings({
  draft,
  saved,
  problems,
  onText,
  onKey,
}: AnthropicSettingsProps) {
  return (
    <>
      <ModelPicker
        draft={draft}
        saved={saved}
        field="anthropic_model"
        problems={problems}
        onText={onText}
        hint="A Claude model id, e.g. claude-sonnet-5-5."
      />
      <TextSetting
        label="Base URL"
        value={draft.text.anthropic_base_url}
        error={problems.anthropic_base_url}
        onChange={(value) => onText("anthropic_base_url", value)}
      />
      <SecretSetting
        label="API key"
        isSet={saved.anthropic_api_key_set}
        draft={draft.keys.anthropic_api_key}
        onChange={(key) => onKey("anthropic_api_key", key)}
      />
    </>
  );
}
