import { PlusIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import type { StyleRecipeDetail, StyleRecipeExport } from "@/api/types";
import { Button } from "@/components/ui/button";
import { INPUT } from "@/components/ui/native-select";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import {
  useCreateStyleRecipe,
  useImportStyleRecipe,
  useStyleTerms,
} from "./styleApi";

const LABEL = "text-body font-medium";

/** The links typed one per line (blank lines dropped). */
function linksOf(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * The form of a new recipe (SPEC-v3 4.1): a name, up to 5 reference links
 * and the rights checkbox with its terms notice, required to create it;
 * onCreated gets the new recipe, which is analyzed from its editor.
 */
export function StyleRecipeForm({
  onCreated,
}: {
  onCreated: (detail: StyleRecipeDetail) => void;
}) {
  const terms = useStyleTerms();
  const create = useCreateStyleRecipe();
  const [name, setName] = useState("");
  const [links, setLinks] = useState("");
  const [rights, setRights] = useState(false);
  const urls = linksOf(links);
  const maxLinks = terms.data?.max_links ?? 5;
  const ready =
    name.trim() !== "" &&
    urls.length > 0 &&
    urls.length <= maxLinks &&
    rights &&
    !create.isPending;
  return (
    <form
      aria-label="New style recipe"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready) return;
        create.mutate(
          {
            name: name.trim(),
            urls: urls as [string, ...string[]],
            rights_confirmed: true,
          },
          {
            onSuccess: (detail) => {
              setName("");
              setLinks("");
              setRights(false);
              onCreated(detail);
            },
          },
        );
      }}
    >
      <h2 className="text-section">New recipe</h2>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="new-recipe-name" className={LABEL}>
          Name
        </label>
        <input
          id="new-recipe-name"
          value={name}
          maxLength={200}
          onChange={(event) => setName(event.target.value)}
          className={cn(INPUT, "h-9")}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="new-recipe-links" className={LABEL}>
          Reference links (one per line, up to {maxLinks})
        </label>
        <textarea
          id="new-recipe-links"
          rows={3}
          value={links}
          placeholder="https://www.youtube.com/shorts/…"
          onChange={(event) => setLinks(event.target.value)}
          className={cn(INPUT, "resize-y py-2")}
        />
        {terms.data && (
          <p className="text-caption text-muted-foreground">
            Each reference is at most {terms.data.max_seconds / 60} min and{" "}
            {terms.data.max_height}p; its media is deleted right after the
            analysis.
          </p>
        )}
      </div>
      <label className="flex items-start gap-2 text-body">
        <input
          type="checkbox"
          checked={rights}
          onChange={(event) => setRights(event.target.checked)}
          className="mt-1 size-4 accent-primary"
        />
        <span>
          I have the right to analyze these videos.
          {terms.data && (
            <span className="block text-caption text-muted-foreground">
              {terms.data.notice}
            </span>
          )}
        </span>
      </label>
      <div>
        <Button type="submit" disabled={!ready}>
          <PlusIcon aria-hidden />
          {create.isPending ? "Creating…" : "Create recipe"}
        </Button>
      </div>
    </form>
  );
}

/** The button that imports an exported recipe file as a new recipe;
 * onImported gets it. A file that is not JSON is refused here, one that
 * is not a recipe by the server. */
export function ImportRecipeButton({
  onImported,
}: {
  onImported: (detail: StyleRecipeDetail) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const importRecipe = useImportStyleRecipe();
  const read = async (file: File) => {
    let body: StyleRecipeExport;
    try {
      body = JSON.parse(await file.text()) as StyleRecipeExport;
    } catch {
      toast.error(`${file.name} is not a recipe file (JSON).`);
      return;
    }
    importRecipe.mutate(body, { onSuccess: onImported });
  };
  return (
    <>
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        aria-label="Recipe file"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void read(file);
        }}
      />
      <Button
        variant="outline"
        disabled={importRecipe.isPending}
        onClick={() => input.current?.click()}
      >
        <UploadSimpleIcon aria-hidden />
        Import JSON
      </Button>
    </>
  );
}
