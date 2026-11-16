import { useEffect, useRef, useState } from "react";

/**
 * Listening to a sound file one at a time: `toggle(url)` plays url (stopping
 * the one that plays) or stops it if it is the one playing; `playing` is the
 * URL that plays now. The sound stops when the component unmounts.
 */
export function useSoundPreview() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => {
    return () => audio.current?.pause();
  }, []);

  const toggle = (url: string) => {
    audio.current?.pause();
    if (playing === url) {
      setPlaying(null);
      return;
    }
    const next = new Audio(url);
    next.onended = () => setPlaying((now) => (now === url ? null : now));
    audio.current = next;
    setPlaying(url);
    next.play().catch(() => setPlaying(null));
  };

  return { playing, toggle };
}
