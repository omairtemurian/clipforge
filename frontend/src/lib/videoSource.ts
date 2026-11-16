export type UrlCheck =
  { ok: true; url: string } | { ok: false; message: string };

const VIDEO_EXTENSIONS = [
  ".mp4",
  ".mov",
  ".mkv",
  ".webm",
  ".avi",
  ".m4v",
  ".mpg",
  ".mpeg",
  ".ts",
];

const BARE_HOST = /^[\w-]+(\.[\w-]+)+([/?#:]|$)/;

/**
 * Check the text of the link input: a http(s) URL with a host.
 *
 * A link typed without a scheme ("youtube.com/watch?v=x") gets "https://".
 * The returned `url` is the trimmed, normalized link to send to the API.
 */
export function checkVideoUrl(text: string): UrlCheck {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, message: "Paste a video link first." };

  const candidate =
    BARE_HOST.test(trimmed) && !trimmed.includes("://")
      ? `https://${trimmed}`
      : trimmed;
  try {
    const parsed = new URL(candidate);
    const web = parsed.protocol === "http:" || parsed.protocol === "https:";
    if (web && parsed.hostname) return { ok: true, url: candidate };
  } catch {
    // Not a URL at all: reported below.
  }
  return {
    ok: false,
    message: "Enter a full video link, like https://youtube.com/watch?v=...",
  };
}

/** True when the file looks like a video (its MIME type or its extension). */
export function isVideoFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  const name = file.name.toLowerCase();
  return VIDEO_EXTENSIONS.some((extension) => name.endsWith(extension));
}

/** The first video among the files, or null when none is a video. */
export function firstVideoFile(files: Iterable<File>): File | null {
  for (const file of files) {
    if (isVideoFile(file)) return file;
  }
  return null;
}
