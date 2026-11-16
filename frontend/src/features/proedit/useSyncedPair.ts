import { useRef, useState, type RefObject } from "react";

/** How far (s) the following video may drift from the leading one before
 * it is sought to the leader's time. */
export const MAX_DRIFT = 0.25;

type VideoRef = RefObject<HTMLVideoElement>;
type Side = "left" | "right";

export interface SyncedPair {
  left: VideoRef;
  right: VideoRef;
  playing: boolean;
  /** Play or pause both videos. */
  toggle: () => void;
  /** Bring the follower to the leader's time, and play it while the pair
   * plays; call it when the follower has loaded. */
  follow: () => void;
  /** The handlers of the left or right video. */
  events: (side: Side) => {
    onTimeUpdate: (e: React.SyntheticEvent<HTMLVideoElement>) => void;
    onPlaying: () => void;
    onEnded: () => void;
  };
}

/**
 * Two videos (left, right) played, paused and kept at the same time
 * together. The right one leads when rightLeads (else the left one): it
 * reports its time to onTime, and the follower starts only once the leader
 * really plays and is sought back to it whenever it drifts (a follower that
 * loads late, e.g. a preview the backend renders on its first request,
 * catches up instead of playing out of sync).
 */
export function useSyncedPair(
  rightLeads: boolean,
  onTime: (t: number) => void,
): SyncedPair {
  const left = useRef<HTMLVideoElement>(null);
  const right = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const leader = rightLeads ? right : left;
  const follower = rightLeads ? left : right;

  const follow = () => {
    const lead = leader.current;
    const other = follower.current;
    if (!lead || !other || other.readyState < HTMLMediaElement.HAVE_METADATA)
      return;
    if (Math.abs(other.currentTime - lead.currentTime) > MAX_DRIFT) {
      other.currentTime = lead.currentTime;
    }
    const before = lead.currentTime < other.duration;
    if (playing && !lead.paused && other.paused && before) {
      void other.play().catch(() => undefined);
    }
  };

  const pause = () => {
    for (const ref of [left, right]) ref.current?.pause();
    setPlaying(false);
  };

  const toggle = () => {
    if (playing) return pause();
    const lead = leader.current;
    if (!lead) return;
    setPlaying(true);
    void lead.play().catch(() => setPlaying(false));
  };

  const events = (side: Side) => {
    const leads = (side === "right") === rightLeads;
    return {
      onTimeUpdate: (e: React.SyntheticEvent<HTMLVideoElement>) => {
        if (!leads) return;
        onTime(e.currentTarget.currentTime);
        follow();
      },
      onPlaying: () => leads && follow(),
      onEnded: () => leads && pause(),
    };
  };

  return { left, right, playing, toggle, follow, events };
}
