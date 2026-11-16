import { PlusIcon } from "@phosphor-icons/react";
import { apiUrl } from "@/api/client";
import type { BrandTemplate } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { choiceClass } from "@/lib/surfaces";

interface BrandListProps {
  templates: BrandTemplate[];
  /** The id of the template being edited; null while a new one is made. */
  selectedId: number | null;
  logoVersion: number;
  onSelect: (id: number) => void;
  onNew: () => void;
}

/** The templates as a column of cards (logo, name, color) and a New button. */
export function BrandList({
  templates,
  selectedId,
  logoVersion,
  onSelect,
  onNew,
}: BrandListProps) {
  return (
    <div className="flex flex-col gap-3">
      <Button
        onClick={onNew}
        variant={selectedId === null ? "secondary" : "default"}
      >
        <PlusIcon aria-hidden />
        New template
      </Button>
      <ul aria-label="Brand templates" className="flex flex-col gap-2">
        {templates.map((template) => (
          <li key={template.id}>
            <button
              type="button"
              onClick={() => onSelect(template.id)}
              aria-current={template.id === selectedId}
              className={cn(
                choiceClass(template.id === selectedId),
                "flex w-full cursor-pointer items-center gap-3",
              )}
            >
              <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted">
                <img
                  src={apiUrl(
                    `/brand-templates/${template.id}/logo?v=${logoVersion}`,
                  )}
                  alt=""
                  className="size-full object-contain"
                  onError={(event) => (event.currentTarget.hidden = true)}
                />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body font-medium">
                  {template.name}
                </span>
                <span className="block truncate text-caption text-muted-foreground">
                  {template.font}
                </span>
              </span>
              <span
                aria-hidden
                className="size-4 shrink-0 rounded-full border border-border"
                style={{ backgroundColor: template.primary_color }}
              />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
