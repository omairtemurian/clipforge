import { AnthropicSettings } from "./AnthropicSettings";
import { ClaudeCodeSettings } from "./ClaudeCodeSettings";
import { ModelPicker } from "./ModelPicker";
import { Section } from "./Section";
import { SecretSetting } from "./SecretSetting";
import { TextSetting } from "./TextSetting";
import { TestConnection } from "./TestConnection";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Field } from "@/components/settings/Field";
import type { SettingsView } from "@/api/types";
import type { LlmProvider } from "@/lib/settingsForm";
import type { SectionProps } from "./sectionProps";

const PROVIDERS: { value: LlmProvider; label: string }[] = [
  { value: "copilot", label: "GitHub Copilot" },
  { value: "openai", label: "OpenAI-compatible" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "anthropic", label: "Anthropic API" },
  { value: "claude_code", label: "Claude subscription (Claude Code)" },
];

interface LlmSectionProps extends SectionProps {
  saved: SettingsView;
  onProvider: (provider: LlmProvider) => void;
}

/** The language model: provider, model, the provider's endpoint and key,
 * and a button that tries the connection. */
export function LlmSection({
  draft,
  saved,
  problems,
  onText,
  onKey,
  onProvider,
}: LlmSectionProps) {
  const provider = draft.llm_provider;
  return (
    <Section
      title="Language model"
      description="Picks the clips and writes their titles."
    >
      <Field label="Provider">
        <ChoiceChips
          label="Provider"
          options={PROVIDERS}
          value={provider}
          onChange={onProvider}
        />
      </Field>
      {provider === "anthropic" && (
        <AnthropicSettings
          draft={draft}
          saved={saved}
          problems={problems}
          onText={onText}
          onKey={onKey}
        />
      )}
      {provider === "claude_code" && (
        <ClaudeCodeSettings draft={draft} problems={problems} onText={onText} />
      )}
      {provider !== "anthropic" && provider !== "claude_code" && (
        <ModelPicker
          key={provider}
          draft={draft}
          saved={saved}
          field="llm_model"
          problems={problems}
          onText={onText}
        />
      )}
      {provider === "openai" && (
        <>
          <TextSetting
            label="Base URL"
            value={draft.text.openai_base_url}
            error={problems.openai_base_url}
            onChange={(value) => onText("openai_base_url", value)}
          />
          <SecretSetting
            label="API key"
            isSet={saved.openai_api_key_set}
            draft={draft.keys.openai_api_key}
            onChange={(key) => onKey("openai_api_key", key)}
          />
        </>
      )}
      {provider === "ollama" && (
        <TextSetting
          label="Ollama host"
          value={draft.text.ollama_host}
          error={problems.ollama_host}
          onChange={(value) => onText("ollama_host", value)}
        />
      )}
      {provider === "copilot" && (
        <>
          <TextSetting
            label="GitHub account"
            value={draft.text.copilot_account}
            error={problems.copilot_account}
            hint="Without a GitHub token, the token of this GitHub CLI account (gh auth token) is used."
            onChange={(value) => onText("copilot_account", value)}
          />
          <SecretSetting
            label="GitHub token"
            isSet={saved.github_copilot_token_set}
            draft={draft.keys.github_copilot_token}
            onChange={(key) => onKey("github_copilot_token", key)}
          />
        </>
      )}
      <TestConnection draft={draft} saved={saved} />
    </Section>
  );
}
