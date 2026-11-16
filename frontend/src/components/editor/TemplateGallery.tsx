import { SquaresFourIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { CaptionTemplateInfo } from "@/api/types";
import { CaptionCarousel } from "@/components/settings/CaptionCarousel";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";

interface TemplateGalleryProps {
  templates: CaptionTemplateInfo[] | undefined;
  value: string;
  onChange: (name: string) => void;
}

/** "All templates": a modal grid of every caption template's preview; a
 * click chooses the template and closes it. */
export function TemplateGallery({
  templates,
  value,
  onChange,
}: TemplateGalleryProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
      >
        <SquaresFourIcon aria-hidden />
        All templates
      </Button>
      {open && (
        <DialogFrame
          wide
          title="Caption templates"
          description="Choose how the captions look. Your colors and size are replaced by the template's."
          onClose={() => setOpen(false)}
        >
          <div className="mt-4">
            <CaptionCarousel
              layout="grid"
              templates={templates}
              value={value}
              onChange={(name) => {
                onChange(name);
                setOpen(false);
              }}
            />
          </div>
        </DialogFrame>
      )}
    </>
  );
}
