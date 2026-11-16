import { DownloadSimpleIcon } from "@phosphor-icons/react";
import { DropdownMenu } from "radix-ui";
import { transcriptUrl, type TranscriptFormat } from "@/api/captions";
import { buttonVariants } from "@/components/ui/button";

interface TranscriptDownloadsProps {
  clipId: number;
  projectId: number;
}

const ITEM =
  "flex cursor-pointer items-center justify-between gap-6 rounded-md px-2.5 py-1.5 text-body outline-none data-highlighted:bg-muted";

const FORMATS: { format: TranscriptFormat; label: string }[] = [
  { format: "txt", label: "Text" },
  { format: "srt", label: "Subtitles" },
  { format: "vtt", label: "Web subtitles" },
];

const GROUPS = [
  { of: "clips", title: "This clip (as saved)" },
  { of: "projects", title: "Whole video" },
] as const;

/**
 * "Download transcript": a menu of the clip's captions (as its render shows
 * them, translated and censored) and of the whole video's transcript, as
 * text (.txt) or subtitles (.srt, .vtt).
 */
export function TranscriptDownloads({
  clipId,
  projectId,
}: TranscriptDownloadsProps) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        aria-label="Download transcript"
        title="Download the transcript or subtitles"
        className={buttonVariants({ variant: "ghost", size: "icon" })}
      >
        <DownloadSimpleIcon aria-hidden />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-56 rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-popover"
        >
          {GROUPS.map(({ of, title }, index) => (
            <DropdownMenu.Group key={of}>
              {index > 0 && (
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
              )}
              <DropdownMenu.Label className="px-2.5 py-1 text-caption text-muted-foreground">
                {title}
              </DropdownMenu.Label>
              {FORMATS.map(({ format, label }) => (
                <DropdownMenu.Item key={format} asChild className={ITEM}>
                  <a
                    href={transcriptUrl(
                      of,
                      of === "clips" ? clipId : projectId,
                      format,
                    )}
                    download
                  >
                    {label}
                    <span className="text-caption text-muted-foreground">
                      .{format}
                    </span>
                  </a>
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Group>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
