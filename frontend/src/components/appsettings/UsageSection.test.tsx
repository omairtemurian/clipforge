import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { SettingsView } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  callsTo,
  json,
  mockRoutes,
  SAVED_SETTINGS,
  usageSummary,
} from "@/testing/mockApi";
import { UsageSection } from "./UsageSection";

function renderSection(saved: SettingsView = SAVED_SETTINGS) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <UsageSection saved={saved} />
      <Toaster />
    </QueryClientProvider>,
  );
}

afterEach(() => act(() => clearToasts()));

describe("UsageSection", () => {
  it("shows the month's totals and the saved caps", async () => {
    mockRoutes({
      "GET /api/usage": () =>
        json(
          usageSummary(
            { compute: 5400, llm_tokens: 12345, api_calls: 3 },
            { llm_tokens: 20000 },
          ),
        ),
    });
    renderSection({ ...SAVED_SETTINGS, usage_cap_llm_tokens: 20000 });

    expect(await screen.findByText("1.50 h")).toBeVisible();
    expect(screen.getByText("12,345")).toBeVisible();
    expect(screen.getByLabelText(/LLM tokens cap/)).toHaveValue("20000");
    expect(screen.getByLabelText(/Compute time cap/)).toHaveValue("");
    expect(screen.queryByText("Cap reached")).toBeNull();
  });

  it("says so when a cap is reached", async () => {
    mockRoutes({
      "GET /api/usage": () =>
        json(usageSummary({ llm_tokens: 500 }, { llm_tokens: 500 })),
    });
    renderSection({ ...SAVED_SETTINGS, usage_cap_llm_tokens: 500 });

    expect(await screen.findByText("Cap reached")).toBeVisible();
  });

  it("saves only the caps that changed", async () => {
    const fetchMock = mockRoutes({
      "GET /api/usage": () => json(usageSummary({ compute: 60 })),
      "PUT /api/settings": () =>
        json({ ...SAVED_SETTINGS, usage_cap_compute_hours: 2.5 }),
    });
    renderSection();
    await screen.findByText("1.0 min");
    const save = screen.getByRole("button", { name: "Save caps" });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/Compute time cap/), "2.5");
    await userEvent.click(save);

    expect(await screen.findByText("Settings saved.")).toBeVisible();
    const [put] = callsTo(fetchMock, "PUT", "/api/settings");
    expect(JSON.parse((put[1] as RequestInit).body as string)).toEqual({
      usage_cap_compute_hours: 2.5,
    });
    expect(screen.getByLabelText(/Compute time cap/)).toHaveValue("2.5");
  });

  it("clears a cap by emptying it and refuses a bad number", async () => {
    const fetchMock = mockRoutes({
      "GET /api/usage": () => json(usageSummary()),
      "PUT /api/settings": () => json(SAVED_SETTINGS),
    });
    renderSection({ ...SAVED_SETTINGS, usage_cap_api_calls: 40 });
    const calls = await screen.findByLabelText(/Paid API calls cap/);

    await userEvent.type(calls, "x");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "A cap must be a number of 0 or more.",
    );
    expect(screen.getByRole("button", { name: "Save caps" })).toBeDisabled();

    await userEvent.clear(calls);
    await userEvent.click(screen.getByRole("button", { name: "Save caps" }));

    await screen.findByText("Settings saved.");
    const [put] = callsTo(fetchMock, "PUT", "/api/settings");
    expect(JSON.parse((put[1] as RequestInit).body as string)).toEqual({
      usage_cap_api_calls: 0,
    });
  });
});
