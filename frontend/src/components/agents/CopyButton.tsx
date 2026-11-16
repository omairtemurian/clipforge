import { useEffect, useRef, useState } from "react";
import { CheckIcon, CopyIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { toast } from "@/lib/toast";

const COPIED_MS = 2000;

/** Copies text to the clipboard and says "Copied" for a moment. */
export function CopyButton({
  text,
  label = "Copy",
  caption = "Copy",
}: {
  text: string;
  /** The accessible name of the button. */
  label?: string;
  /** The words shown on the button before it is clicked. */
  caption?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      toast.error("Could not copy. Select the text and copy it by hand.");
      return;
    }
    setCopied(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), COPIED_MS);
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={label}
      onClick={() => void copy()}
    >
      {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
      {copied ? "Copied" : caption}
    </Button>
  );
}
