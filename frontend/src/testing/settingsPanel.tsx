import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { ProcessingSettings, SourceInfo } from "@/api/types";
import { SettingsPanel } from "@/components/SettingsPanel";
import type { RightsChoice } from "@/lib/sourceRights";
import {
  DEFAULTS,
  captionTemplate,
  json,
  mockRoutes,
  REFRAME_PRESETS,
  type Handler,
} from "./mockApi";

export const URL = "https://youtu.be/a";
export const INFO: SourceInfo = {
  url: URL,
  title: "Late night set",
  duration: 754,
  thumbnail_url: "https://img.example/a.jpg",
};
const BRANDS = [
  { id: 4, name: "Studio" },
  { id: 9, name: "Podcast look" },
];
const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "fr", name: "French" },
];

/** The API routes the settings panel reads, plus extra ones. */
export function panelRoutes(extra: Record<string, Handler> = {}) {
  return mockRoutes({
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "POST /api/sources/probe": () => json(INFO),
    "GET /api/caption-templates": () =>
      json(["boxed", "karaoke_bold", "minimal"].map(captionTemplate)),
    "GET /api/brand-templates": () => json(BRANDS),
    "GET /api/speech-languages": () => json(LANGUAGES),
    "GET /api/processing-presets": () => json([]),
    "GET /api/reframe-presets": () => json(REFRAME_PRESETS),
    ...extra,
  });
}

/** Render the settings panel for URL; returns its onSubmit and onClose. */
export function renderPanel(busy = false) {
  const onSubmit =
    vi.fn<(settings: ProcessingSettings, rights: RightsChoice) => void>();
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <SettingsPanel
        source={{ url: URL }}
        busy={busy}
        onSubmit={onSubmit}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { onSubmit, onClose };
}

/** Choose the required source rights, then press "Get clips". */
export async function getClips(
  user: ReturnType<typeof userEvent.setup>,
  rights = "own",
) {
  await user.selectOptions(screen.getByLabelText("Source rights"), rights);
  await user.click(screen.getByRole("button", { name: "Get clips" }));
}
