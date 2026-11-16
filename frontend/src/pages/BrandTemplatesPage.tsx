import { useState } from "react";
import { useBrandTemplates } from "@/api/templates";
import { BrandForm } from "@/components/brand/BrandForm";
import { BrandList } from "@/components/brand/BrandList";
import { PageHeader } from "@/components/PageHeader";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** Brand templates: the saved ones on the left, the form of the chosen one
 * (or of a new one) with its live preview on the right. */
export function BrandTemplatesPage() {
  const brands = useBrandTemplates();
  // undefined: the first template (or a new one when there is none).
  const [chosen, setChosen] = useState<number | "new" | undefined>();
  const templates = brands.data ?? [];
  const selected =
    chosen === "new"
      ? undefined
      : (templates.find((t) => t.id === chosen) ?? templates[0]);
  const creating = brands.isSuccess && selected === undefined;

  return (
    <>
      <PageHeader
        title="Brand templates"
        description="Logo, intro, outro and colors that you apply to clips."
      />
      <div
        className={cn(
          pageColumn(),
          "grid gap-6 pb-10 md:grid-cols-[16rem_1fr]",
        )}
      >
        <BrandList
          templates={templates}
          selectedId={selected?.id ?? null}
          logoVersion={brands.dataUpdatedAt}
          onSelect={setChosen}
          onNew={() => setChosen("new")}
        />
        {brands.isError && (
          <p role="alert" className="text-body text-destructive">
            Could not load the brand templates.
          </p>
        )}
        {(creating || selected) && (
          <BrandForm
            key={selected?.id ?? "new"}
            template={selected}
            logoVersion={brands.dataUpdatedAt}
            onSaved={(saved) => setChosen(saved.id)}
            onDeleted={() => setChosen(undefined)}
          />
        )}
      </div>
    </>
  );
}
