import type { CaptionStyle, CaptionTemplate } from "@/api/types";
import { CaptionSample } from "@/components/editor/CaptionSample";
import { useCaptionPreview } from "@/hooks/useCaptionPreview";
import { templateFields } from "@/lib/clipLook";

interface CaptionPreviewProps {
  /** The template's name and its fields with the style applied. */
  name: string;
  template: CaptionTemplate;
  style: CaptionStyle;
}

/** The live preview of the caption style: the backend's drawing of the
 * template's sample caption on a 9:16 frame (font, stroke, box, position
 * and all), and the quick sample line until it is drawn or if it cannot
 * be. */
export function CaptionPreview({ name, template, style }: CaptionPreviewProps) {
  const preview = useCaptionPreview(name, templateFields(style));
  if (!preview.url || preview.failed) {
    return <CaptionSample template={template} />;
  }
  return (
    <div className="flex justify-center">
      <img
        src={preview.url}
        alt="Caption preview"
        className="aspect-[9/16] w-40 rounded-lg border border-border object-cover"
      />
    </div>
  );
}
