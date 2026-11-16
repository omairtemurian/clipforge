import { TextSetting } from "./TextSetting";
import type { SectionProps } from "./sectionProps";

/** The Claude subscription provider: the model and the Claude Code program
 * it runs (logged in from a terminal; no key is stored here). */
export function ClaudeCodeSettings({
  draft,
  problems,
  onText,
}: Omit<SectionProps, "onKey">) {
  return (
    <>
      <TextSetting
        label="Model"
        value={draft.text.claude_code_model}
        error={problems.claude_code_model}
        hint="An alias (sonnet, opus, fable) or a full Claude model id."
        onChange={(value) => onText("claude_code_model", value)}
      />
      <TextSetting
        label="Claude Code program"
        value={draft.text.claude_code_bin}
        error={problems.claude_code_bin}
        hint="Uses your Claude subscription: run claude in a terminal once and log in."
        onChange={(value) => onText("claude_code_bin", value)}
      />
    </>
  );
}
