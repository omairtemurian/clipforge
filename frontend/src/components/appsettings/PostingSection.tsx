import { useId } from "react";
import { Field } from "@/components/settings/Field";
import { HashtagChips } from "@/components/settings/HashtagChips";
import { NativeSelect } from "@/components/ui/native-select";
import type { MissedPolicy } from "@/lib/settingsForm";
import { Section } from "./Section";

const MISSED_POLICIES: { value: MissedPolicy; label: string }[] = [
  { value: "post_late", label: "Post them late" },
  { value: "skip", label: "Skip them" },
];

interface PostingSectionProps {
  value: string[];
  onChange: (tags: string[]) => void;
  missedPolicy: MissedPolicy;
  onMissedPolicy: (policy: MissedPolicy) => void;
}

/** How posts are written and sent: the hashtags that every post gets and
 * what happens to posts that came due while ClipForge was off. */
export function PostingSection({
  value,
  onChange,
  missedPolicy,
  onMissedPolicy,
}: PostingSectionProps) {
  const id = useId();
  return (
    <Section
      title="Posting"
      description="What every post you publish or schedule gets."
    >
      <HashtagChips
        label="Always include these hashtags"
        value={value}
        onChange={onChange}
        hint="Added to the description and caption of every post, next to the campaign's required hashtags. A shorter AI text or a “no hashtags” rewrite never removes them; you can still delete them by hand in a post."
      />
      <Field label="Posts missed while ClipForge was off" htmlFor={id}>
        <NativeSelect
          id={id}
          value={missedPolicy}
          aria-describedby={`${id}-hint`}
          onChange={(event) =>
            onMissedPolicy(event.target.value as MissedPolicy)
          }
          block
        >
          {MISSED_POLICIES.map((policy) => (
            <option key={policy.value} value={policy.value}>
              {policy.label}
            </option>
          ))}
        </NativeSelect>
        <p id={`${id}-hint`} className="text-caption text-muted-foreground">
          Scheduled posts go out in the background while ClipForge runs, even
          with this window closed. A post whose time passed while it was off
          goes out on the next start, or is marked Skipped so you can still post
          it by hand.
        </p>
      </Field>
    </Section>
  );
}
