/**
 * The post details sheet of the calendar: the form fields of a saved post
 * (from the PostText its payload was built from, the clip's own texts
 * where it had none) and the PostText of PATCH /posts/{id} after an edit,
 * which keeps every field the user did not touch as it was (so a post
 * that took the clip's hashtags still gets the required ones).
 */
import type { Clip, Post, PostText } from "@/api/types";
import { formatHashtags, parseHashtags } from "@/lib/clipText";
import {
  POST_PLATFORMS,
  PRIVACY_CHOICES,
  hasTitle,
  type PostFields,
  type PostPlatform,
} from "@/lib/postForm";

type ClipTexts = Pick<Clip, "title" | "description" | "hashtags">;

const EMPTY_TEXT: PostText = {
  title: null,
  caption: null,
  hashtags: null,
  link: null,
  privacy: null,
  collaborators: [],
  options: {},
};

/** Whether the sheet can edit the text of a post on platform. */
export function isPostPlatform(platform: string): platform is PostPlatform {
  return (POST_PLATFORMS as readonly string[]).includes(platform);
}

/** Whether the post's text and time may still change. */
export function isEditable(post: Post): boolean {
  return post.status === "draft" || post.status === "queued";
}

/** The PostText the post's payload was built from. */
export function textOf(post: Post): PostText {
  const text = post.payload.text;
  return text && typeof text === "object"
    ? { ...EMPTY_TEXT, ...(text as Partial<PostText>) }
    : EMPTY_TEXT;
}

/** The non-blank parts as paragraphs, like the backend's captions. */
function paragraphs(...parts: string[]): string {
  return parts
    .map((part) => part.trim())
    .filter(Boolean)
    .join("\n\n");
}

/** The form fields of a post as it will go out: its own text, the clip's
 * where it has none (a platform without titles shows the title at the
 * top of the caption). */
export function editFieldsOf(
  platform: PostPlatform,
  text: PostText,
  clip: ClipTexts,
): PostFields {
  const title = text.title ?? clip.title;
  const description = text.caption ?? clip.description;
  const titled = hasTitle(platform);
  return {
    title: titled ? title : "",
    caption: titled ? description : paragraphs(title, description),
    hashtags: formatHashtags(text.hashtags ?? clip.hashtags),
    privacy:
      text.privacy ??
      (platform === "tiktok" ? "" : PRIVACY_CHOICES[platform][0].value),
  };
}

/** The post's new PostText: the original's fields, with those the user
 * changed (current differs from initial) taken from the form. */
export function editedText(
  platform: PostPlatform,
  original: PostText,
  initial: PostFields,
  current: PostFields,
): PostText {
  const titled = hasTitle(platform);
  const text = { ...original };
  if (current.title !== initial.title) text.title = current.title.trim();
  if (current.caption !== initial.caption) {
    text.caption = current.caption;
    if (!titled) text.title = "";
  }
  if (current.hashtags !== initial.hashtags) {
    text.hashtags = parseHashtags(current.hashtags);
  }
  if (current.privacy !== initial.privacy) {
    text.privacy = current.privacy || null;
  }
  return text;
}

/** Whether the form differs from the post's fields. */
export function fieldsChanged(initial: PostFields, current: PostFields) {
  return (Object.keys(initial) as (keyof PostFields)[]).some(
    (key) => initial[key] !== current[key],
  );
}
