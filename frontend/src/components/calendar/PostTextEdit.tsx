import { useState } from "react";
import { useUpdatePost } from "@/api/posts";
import type { Clip, Post } from "@/api/types";
import { PostFieldsForm } from "@/components/posts/PostFieldsForm";
import { Button } from "@/components/ui/button";
import {
  editFieldsOf,
  editedText,
  fieldsChanged,
  textOf,
} from "@/lib/postEdit";
import type { PostPlatform } from "@/lib/postForm";
import { toast } from "@/lib/toast";

interface PostTextEditProps {
  post: Post;
  platform: PostPlatform;
  clip: Clip;
}

/** The sheet's text of a draft or scheduled post, saved with "Save text";
 * the fields left alone keep what the post had. */
export function PostTextEdit({ post, platform, clip }: PostTextEditProps) {
  const update = useUpdatePost();
  const original = textOf(post);
  const [initial] = useState(() => editFieldsOf(platform, original, clip));
  const [fields, setFields] = useState(initial);
  const changed = fieldsChanged(initial, fields);

  function save() {
    update.mutate(
      {
        id: post.id,
        patch: { text: editedText(platform, original, initial, fields) },
      },
      { onSuccess: () => toast.success("Post text saved.") },
    );
  }

  return (
    <section aria-label="Post text" className="flex flex-col gap-3">
      <PostFieldsForm
        platform={platform}
        fields={fields}
        onChange={setFields}
        idPrefix="post-editor"
      />
      <Button
        className="self-end"
        disabled={!changed || update.isPending}
        onClick={save}
      >
        Save text
      </Button>
    </section>
  );
}
