import { PauseIcon, PlayIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

interface PreviewButtonProps {
  /** What the sound is called, for the button's name. */
  name: string;
  playing: boolean;
  onToggle: () => void;
}

/** A small round button that plays or pauses a sound's preview. */
export function PreviewButton({ name, playing, onToggle }: PreviewButtonProps) {
  return (
    <Button
      type="button"
      size="icon"
      variant="outline"
      aria-label={`${playing ? "Pause" : "Play"} ${name}`}
      aria-pressed={playing}
      onClick={onToggle}
      className="size-8 shrink-0"
    >
      {playing ? <PauseIcon aria-hidden /> : <PlayIcon aria-hidden />}
    </Button>
  );
}
