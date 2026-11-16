import type { CaptionTemplate } from "@/api/types";

/** A line of sample words as the template draws them: the spoken word in
 * the highlight color, an emphasis word in its color, the rest in the main
 * color. The sizes are scaled down from the output frame's pixels. */
export function CaptionSample({ template }: { template: CaptionTemplate }) {
  const word = (text: string, color: string) => (
    <span style={{ color }}>{text} </span>
  );
  return (
    <div
      aria-label="Caption sample"
      className="flex h-28 items-center justify-center overflow-hidden rounded-lg bg-black/70 px-3 text-center"
    >
      <p
        className={`leading-tight font-bold ${template.uppercase ? "uppercase" : ""}`}
        style={{ fontSize: Math.max(10, template.size / 4) }}
      >
        {word("Wait,", template.primary_color)}
        {word("my", template.highlight_color)}
        {word("brother", template.emphasis_color)}
        {word("ate it", template.primary_color)}
        {template.emoji && <span aria-hidden>🍕</span>}
      </p>
    </div>
  );
}
