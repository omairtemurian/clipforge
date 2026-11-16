import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type VideoHTMLAttributes,
} from "react";

/** What the editor needs from its preview <video>. */
export interface PreviewPlayer {
  /** Pass as the <video>'s ref. */
  attach: (video: HTMLVideoElement | null) => void;
  playing: boolean;
  /** The preview's current time in seconds. */
  time: number;
  toggle: () => void;
  /** Jump to t seconds of the preview. */
  seek: (t: number) => void;
  /** The playback speed (1: normal), kept when the <video> changes. */
  rate: number;
  setRate: (rate: number) => void;
  /** Spread on the <video> to keep playing and time in sync. */
  events: Pick<
    VideoHTMLAttributes<HTMLVideoElement>,
    "onPlay" | "onPause" | "onEnded" | "onTimeUpdate" | "onSeeked"
  >;
}

/** Play video at rate, also after it loads a new source (loading resets
 * playbackRate to defaultPlaybackRate). */
function applyRate(video: HTMLVideoElement, rate: number) {
  video.defaultPlaybackRate = rate;
  video.playbackRate = rate;
}

/**
 * State of a preview player: whether it plays and its current time, read
 * every animation frame while playing (timeupdate fires only ~4x a second)
 * so the timeline's playhead moves smoothly, and its playback speed.
 */
export function usePreviewPlayer(): PreviewPlayer {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [rate, setRateValue] = useState(1);
  const rateRef = useRef(1);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      setTime(videoRef.current?.currentTime ?? 0);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const attach = useCallback((video: HTMLVideoElement | null) => {
    videoRef.current = video;
    if (video) applyRate(video, rateRef.current);
  }, []);

  const setRate = useCallback((next: number) => {
    rateRef.current = next;
    if (videoRef.current) applyRate(videoRef.current, next);
    setRateValue(next);
  }, []);

  const toggle = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play().catch(() => setPlaying(false));
    else video.pause();
  }, []);

  const seek = useCallback((t: number) => {
    const video = videoRef.current;
    if (video) video.currentTime = t;
    setTime(t);
  }, []);

  const sync = useCallback(
    () => setTime(videoRef.current?.currentTime ?? 0),
    [],
  );

  return {
    attach,
    playing,
    time,
    toggle,
    seek,
    rate,
    setRate,
    events: {
      onPlay: () => setPlaying(true),
      onPause: () => setPlaying(false),
      onEnded: () => setPlaying(false),
      onTimeUpdate: sync,
      onSeeked: sync,
    },
  };
}
