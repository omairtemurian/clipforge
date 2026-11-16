import { useId } from "react";

import { cn } from "@/lib/utils";

/**
 * ClipForge mark: a vertical short in front of two tilted ones, with a play
 * button. Drawn inline so it follows the theme and needs no network request.
 */
export function LogoMark({ className }: { className?: string }) {
  const gradient = `logo-gradient-${useId()}`;
  return (
    <svg
      viewBox="0 0 64 64"
      role="img"
      aria-hidden="true"
      className={cn("size-8 shrink-0", className)}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ff8a4c" />
          <stop offset="1" stopColor="#e5481c" />
        </linearGradient>
      </defs>
      <rect
        x="9"
        y="12"
        width="22"
        height="40"
        rx="6"
        fill="#ff6b35"
        opacity="0.35"
        transform="rotate(-12 20 32)"
      />
      <rect
        x="33"
        y="12"
        width="22"
        height="40"
        rx="6"
        fill="#ff6b35"
        opacity="0.35"
        transform="rotate(12 44 32)"
      />
      <rect
        x="20"
        y="8"
        width="24"
        height="48"
        rx="7"
        fill={`url(#${gradient})`}
      />
      <path
        d="M28.5 24v16l12-8z"
        fill="#fff"
        stroke="#fff"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}
