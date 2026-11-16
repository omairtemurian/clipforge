import { useEffect, useState } from "react";
import type { VideoSource } from "@/api/projects";
import { useLinkInfo } from "@/api/sources";

/** What the settings panel shows about the chosen video. */
export interface SourceDetails {
  title: string;
  /** Seconds; null while unknown. */
  duration: number | null;
  /** A thumbnail image URL (links). */
  imageUrl: string | null;
  /** A local object URL of the file, shown as a paused video (files). */
  videoUrl: string | null;
  loading: boolean;
  /** Why the link cannot be used, or null. */
  error: string | null;
  retry: () => void;
}

interface FileInfo {
  file: File;
  url: string;
  duration: number | null;
}

/**
 * Read a video file's duration from its metadata in the browser.
 *
 * The object URL lives as long as the file is shown; it is revoked when the
 * file changes or the component unmounts.
 */
function useFileInfo(file: File | null): FileInfo | null {
  const [info, setInfo] = useState<FileInfo | null>(null);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    const done = () => {
      const seconds = Number.isFinite(video.duration) ? video.duration : null;
      setInfo({ file, url, duration: seconds && seconds > 0 ? seconds : null });
    };
    video.addEventListener("loadedmetadata", done);
    video.addEventListener("error", done);
    video.src = url;
    return () => {
      video.removeEventListener("loadedmetadata", done);
      video.removeEventListener("error", done);
      video.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [file]);

  return info && info.file === file ? info : null;
}

function fileTitle(name: string): string {
  return name.replace(/\.[^.]+$/, "") || name;
}

/** Title, duration and thumbnail of a video link, file or Drive video. */
export function useSourceDetails(source: VideoSource): SourceDetails {
  const url = "url" in source ? source.url : null;
  const file = "file" in source ? source.file : null;
  const link = useLinkInfo(url);
  const local = useFileInfo(file);

  if ("drive" in source) {
    return {
      title: fileTitle(source.drive.name),
      duration: source.drive.duration,
      imageUrl: null,
      videoUrl: null,
      loading: false,
      error: null,
      retry: () => {},
    };
  }
  if (file) {
    return {
      title: fileTitle(file.name),
      duration: local?.duration ?? null,
      imageUrl: null,
      videoUrl: local?.url ?? null,
      loading: local === null,
      error: null,
      retry: () => {},
    };
  }
  return {
    title: link.data?.title || (url ?? ""),
    duration: link.data?.duration ?? null,
    imageUrl: link.data?.thumbnail_url ?? null,
    videoUrl: null,
    loading: link.isPending,
    error: link.error?.message ?? null,
    retry: () => void link.refetch(),
  };
}
