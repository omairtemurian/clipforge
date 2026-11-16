import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  callsTo,
  DEFAULTS,
  engineStatus,
  json,
  mockRoutes,
  SAVED_SETTINGS as SAVED,
  usageSummary,
} from "@/testing/mockApi";
import { SettingsPage } from "./SettingsPage";

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function routes(extra: Parameters<typeof mockRoutes>[0] = {}) {
  return mockRoutes({
    "GET /api/settings": () => json(SAVED),
    "GET /api/engines": () => json([engineStatus("kokoro", true)]),
    "GET /api/usage": () => json(usageSummary()),
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "GET /api/speech-languages": () =>
      json([
        { code: "en", name: "English" },
        { code: "de", name: "German" },
      ]),
    "GET /api/accounts/platforms": () =>
      json([
        {
          platform: "youtube",
          supported: true,
          configured: true,
          settings_keys: [],
        },
        {
          platform: "tiktok",
          supported: true,
          configured: false,
          settings_keys: [],
        },
      ]),
    "GET /api/accounts": () =>
      json([
        {
          id: 1,
          platform: "youtube",
          external_id: "x",
          display_name: "Me",
          token_ref: "t",
          scopes: [],
          connected_at: "2026-11-01T10:00:00",
          restrictions: [],
          is_default: true,
          avatar_url: null,
          always_hashtags: [],
        },
      ]),
    "GET /api/notifications/channels": () =>
      json({ email: false, email_to: null, desktop: false }),
    ...extra,
  });
}

function bodyOf(call: unknown[]) {
  return JSON.parse((call[1] as RequestInit).body as string) as unknown;
}

afterEach(() => act(() => clearToasts()));

describe("Settings v2 sections", () => {
  it("shows every section, with the engine status from /api/engines", async () => {
    routes();
    renderPage();

    for (const name of [
      "Language model",
      "Defaults for new projects",
      "Platform connections",
      "Notifications",
      "Usage",
      "Storage paths",
      "Engines",
    ]) {
      expect(await screen.findByRole("region", { name })).toBeVisible();
    }
    const engines = screen.getByRole("region", { name: "Engines" });
    expect(await within(engines).findByText("Engine kokoro")).toBeVisible();
    expect(within(engines).getByText("Installed 1.0")).toBeVisible();
  });

  it("lists the platforms with their accounts and app keys", async () => {
    routes();
    renderPage();

    const region = await screen.findByRole("region", {
      name: "Platform connections",
    });
    const youtube = (await within(region).findByText("YouTube")).closest("li")!;
    expect(within(youtube).getByText("1 account")).toBeVisible();
    expect(within(youtube).getByText("App keys set")).toBeVisible();
    const tiktok = within(region).getByText("TikTok").closest("li")!;
    expect(within(tiktok).getByText("0 accounts")).toBeVisible();
    expect(within(tiktok).getByText("App keys missing")).toBeVisible();
    expect(
      within(region).getByRole("link", { name: "Manage social accounts" }),
    ).toHaveAttribute("href", "/accounts");
  });

  it("saves the notification settings and masks the SMTP password", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({
          ...SAVED,
          smtp_host: "mail.example",
          smtp_port: 465,
          smtp_password_set: true,
        }),
    });
    renderPage();
    const region = await screen.findByRole("region", { name: "Notifications" });

    const password = within(region).getByLabelText("SMTP password");
    expect(password).toHaveAttribute("type", "password");
    await userEvent.type(
      within(region).getByLabelText("SMTP server"),
      "mail.example",
    );
    await userEvent.clear(within(region).getByLabelText("SMTP port"));
    await userEvent.type(within(region).getByLabelText("SMTP port"), "465");
    await userEvent.type(password, "hunter2");
    await userEvent.click(
      within(region).getByRole("button", { name: "Save notifications" }),
    );

    expect(await screen.findByText("Settings saved.")).toBeVisible();
    const [call] = callsTo(fetchMock, "PUT", "/api/settings");
    expect(bodyOf(call)).toEqual({
      smtp_host: "mail.example",
      smtp_port: 465,
      smtp_password: "hunter2",
    });
    expect(within(region).getByLabelText("SMTP password")).toHaveValue("");
    expect(within(region).getByText("Saved")).toBeVisible();
    expect(document.body.innerHTML).not.toContain("hunter2");
  });

  it("refuses a bad port without calling the server", async () => {
    const fetchMock = routes();
    renderPage();
    const region = await screen.findByRole("region", { name: "Notifications" });

    await userEvent.clear(within(region).getByLabelText("SMTP port"));
    await userEvent.type(within(region).getByLabelText("SMTP port"), "99999");
    await userEvent.click(
      within(region).getByRole("button", { name: "Save notifications" }),
    );

    expect(within(region).getByRole("alert")).toHaveTextContent(
      "Enter a port from 1 to 65535.",
    );
    expect(callsTo(fetchMock, "PUT", "/api/settings")).toHaveLength(0);
  });

  it("saves the time of the daily digest and refuses a bad one", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () => json({ ...SAVED, digest_time: "07:30" }),
    });
    renderPage();
    const region = await screen.findByRole("region", { name: "Notifications" });
    const field = within(region).getByLabelText("Daily digest at");
    expect(field).toHaveValue("08:00");
    const save = within(region).getByRole("button", {
      name: "Save notifications",
    });

    await userEvent.clear(field);
    await userEvent.type(field, "7am");
    await userEvent.click(save);
    expect(within(region).getByRole("alert")).toHaveTextContent(
      "Enter a time like 08:00, or leave it blank.",
    );
    expect(callsTo(fetchMock, "PUT", "/api/settings")).toHaveLength(0);

    await userEvent.clear(field);
    await userEvent.type(field, "07:30");
    await userEvent.click(save);

    expect(await screen.findByText("Settings saved.")).toBeVisible();
    const [call] = callsTo(fetchMock, "PUT", "/api/settings");
    expect(bodyOf(call)).toEqual({ digest_time: "07:30" });
  });

  it("sends a test notification", async () => {
    const fetchMock = routes({
      "POST /api/notifications/test": () =>
        json({
          id: 1,
          kind: "test",
          title: "Test notification",
          body: "",
          link: "/settings",
          created_at: "2026-11-02T10:00:00",
          read_at: null,
        }),
    });
    renderPage();
    const region = await screen.findByRole("region", { name: "Notifications" });

    await userEvent.click(
      within(region).getByRole("button", { name: "Send a test" }),
    );

    expect(await screen.findByText(/Test notification sent/)).toBeVisible();
    expect(callsTo(fetchMock, "POST", "/api/notifications/test")).toHaveLength(
      1,
    );
  });

  it("saves the default speech language of new projects", async () => {
    const fetchMock = routes({
      "PUT /api/processing-defaults": () =>
        json({ ...DEFAULTS, language: "de" }),
    });
    renderPage();
    const region = await screen.findByRole("region", {
      name: "Defaults for new projects",
    });
    const button = within(region).getByRole("button", {
      name: "Save default language",
    });
    expect(button).toBeDisabled();

    await within(region).findByRole("option", { name: "German" });
    await userEvent.selectOptions(
      within(region).getByLabelText("Speech language"),
      "de",
    );
    await userEvent.click(button);

    expect(await screen.findByText(/Saved as the default/)).toBeVisible();
    const [call] = callsTo(fetchMock, "PUT", "/api/processing-defaults");
    expect(bodyOf(call)).toMatchObject({ language: "de", subtitles_id: null });
  });
});
