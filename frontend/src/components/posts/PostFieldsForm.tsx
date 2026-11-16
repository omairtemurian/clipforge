import { Field, INPUT } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import {
  PRIVACY_CHOICES,
  hasTitle,
  type PostFields,
  type PostPlatform,
} from "@/lib/postForm";
import { cn } from "@/lib/utils";

interface PostFieldsFormProps {
  platform: PostPlatform;
  fields: PostFields;
  onChange: (fields: PostFields) => void;
  /** Prefix of the inputs' ids (unique on the page). */
  idPrefix: string;
  /** Shown in blank title/caption/hashtags fields. */
  placeholders?: Partial<Record<"title" | "caption" | "hashtags", string>>;
}

/** What a post says on one platform: title where the platform has one,
 * description or caption, hashtags and who can see it. */
export function PostFieldsForm({
  platform,
  fields,
  onChange,
  idPrefix,
  placeholders = {},
}: PostFieldsFormProps) {
  const set = (change: Partial<PostFields>) =>
    onChange({ ...fields, ...change });
  const id = (name: string) => `${idPrefix}-${platform}-${name}`;

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3">
      {hasTitle(platform) && (
        <Field label="Title" htmlFor={id("title")}>
          <input
            id={id("title")}
            value={fields.title}
            placeholder={placeholders.title}
            onChange={(event) => set({ title: event.target.value })}
            className={cn(INPUT, "h-9")}
          />
        </Field>
      )}
      <Field
        label={hasTitle(platform) ? "Description" : "Caption"}
        htmlFor={id("caption")}
        aside={fields.caption.length}
      >
        <textarea
          id={id("caption")}
          rows={5}
          value={fields.caption}
          placeholder={placeholders.caption}
          onChange={(event) => set({ caption: event.target.value })}
          className={cn(INPUT, "resize-none py-2")}
        />
      </Field>
      <Field label="Hashtags" htmlFor={id("hashtags")}>
        <input
          id={id("hashtags")}
          value={fields.hashtags}
          placeholder={placeholders.hashtags}
          onChange={(event) => set({ hashtags: event.target.value })}
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <Field label="Who can see it" htmlFor={id("privacy")}>
        <NativeSelect
          id={id("privacy")}
          value={fields.privacy}
          disabled={PRIVACY_CHOICES[platform].length === 1}
          onChange={(event) => set({ privacy: event.target.value })}
          block
        >
          {platform === "tiktok" && (
            <option value="" disabled>
              Choose who can see it
            </option>
          )}
          {PRIVACY_CHOICES[platform].map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </div>
  );
}
