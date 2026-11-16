import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import type { DriveFile } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  DEFAULTS,
  callsTo,
  json,
  mockRoutes,
  project,
} from "@/testing/mockApi";
import { HomePage } from "./HomePage";

const FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345";
const DRIVE_FILE: DriveFile = {
  id: FILE_ID,
  name: "Team offsite talk.mp4",
  mime_type: "video/mp4",
  size: 4096,
  duration: 754,
};

function renderHome() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function homeRoutes(extra: Parameters<typeof mockRoutes>[0]) {
  return mockRoutes({
    "GET /api/projects": () => json([]),
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "GET /api/caption-templates": () => json([]),
    "GET /api/brand-templates": () => json([]),
    ...extra,
  });
}

async function openDrive() {
  const user = userEvent.setup();
  renderHome();
  await screen.findByText("No projects yet");
  await user.click(screen.getByRole("button", { name: "Google Drive" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Import from Google Drive",
  });
  return { user, dialog };
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Home Google Drive import", () => {
  it("explains the missing credentials with a link to the setup", async () => {
    const fetchMock = homeRoutes({
      "GET /api/sources/gdrive": () =>
        json({ configured: false, connected: false }),
    });
    const { dialog } = await openDrive();

    expect(
      await within(dialog).findByText("Google Drive needs credentials"),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("link", { name: "See setup" }),
    ).toHaveAttribute("href", expect.stringContaining("#google-drive-import"));
    expect(
      within(dialog).queryByRole("button", { name: /Connect/ }),
    ).toBeNull();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method)).toEqual([]);
  });

  it("opens the Google consent in a new window", async () => {
    const popup = { location: { href: "" }, close: vi.fn() };
    const open = vi.fn(() => popup);
    vi.stubGlobal("open", open);
    homeRoutes({
      "GET /api/sources/gdrive": () =>
        json({ configured: true, connected: false }),
      "POST /api/sources/gdrive/connect": () =>
        json({
          authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1",
        }),
    });
    const { user, dialog } = await openDrive();

    await user.click(
      await within(dialog).findByRole("button", {
        name: "Connect Google Drive",
      }),
    );

    expect(
      await within(dialog).findByText(/Finish in the Google window/),
    ).toBeVisible();
    expect(open).toHaveBeenCalledWith("", "_blank");
    expect(popup.location.href).toBe(
      "https://accounts.google.com/o/oauth2/v2/auth?x=1",
    );
  });

  it("reads a Drive link, then imports it with the panel's settings", async () => {
    const created = project({ id: 7, status: "queued" });
    const fetchMock = homeRoutes({
      "GET /api/sources/gdrive": () =>
        json({ configured: true, connected: true }),
      "POST /api/sources/gdrive/file": () => json(DRIVE_FILE),
      "POST /api/sources/gdrive/import": () => json(created, 201),
    });
    const { user, dialog } = await openDrive();
    const link = `https://drive.google.com/file/d/${FILE_ID}/view`;

    await user.type(await within(dialog).findByLabelText("Drive link"), link);
    await user.click(within(dialog).getByRole("button", { name: "Continue" }));

    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(within(panel).getByText("Team offsite talk")).toBeVisible();
    expect(within(panel).getAllByText("12:34")).not.toHaveLength(0);
    expect(
      screen.queryByRole("dialog", { name: "Import from Google Drive" }),
    ).toBeNull();
    const [lookup] = callsTo(fetchMock, "POST", "/api/sources/gdrive/file");
    expect(JSON.parse(lookup[1]?.body as string)).toEqual({ file: link });

    await user.selectOptions(
      within(panel).getByLabelText("Source rights"),
      "own",
    );
    await user.click(within(panel).getByRole("button", { name: "Get clips" }));

    expect(
      await screen.findByText(/ClipForge is looking for clips/),
    ).toBeVisible();
    const [post] = callsTo(fetchMock, "POST", "/api/sources/gdrive/import");
    expect(JSON.parse(post[1]?.body as string)).toEqual({
      file: FILE_ID,
      settings: DEFAULTS,
      source_rights: "own",
      credit_line: "",
    });
  });

  it("shows why a Drive link cannot be used", async () => {
    homeRoutes({
      "GET /api/sources/gdrive": () =>
        json({ configured: true, connected: true }),
      "POST /api/sources/gdrive/file": () =>
        json(
          { error: "drive_file_not_found", message: "Drive has no such file." },
          404,
        ),
    });
    const { user, dialog } = await openDrive();

    await user.type(
      await within(dialog).findByLabelText("Drive link"),
      FILE_ID,
    );
    await user.click(within(dialog).getByRole("button", { name: "Continue" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Drive has no such file.",
    );
    expect(screen.queryByRole("dialog", { name: "Clip settings" })).toBeNull();
  });

  it("disconnects the account", async () => {
    let connected = true;
    const fetchMock = homeRoutes({
      "GET /api/sources/gdrive": () => json({ configured: true, connected }),
      "DELETE /api/sources/gdrive/connection": () => {
        connected = false;
        return new Response(null, { status: 204 });
      },
    });
    const { user, dialog } = await openDrive();

    await user.click(
      await within(dialog).findByRole("button", { name: "Disconnect" }),
    );

    expect(
      await within(dialog).findByRole("button", {
        name: "Connect Google Drive",
      }),
    ).toBeVisible();
    expect(
      callsTo(fetchMock, "DELETE", "/api/sources/gdrive/connection"),
    ).toHaveLength(1);
  });
});
