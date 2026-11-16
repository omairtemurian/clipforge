import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { callsTo, engineStatus, json, mockRoutes } from "@/testing/mockApi";
import { EnginesSection } from "./EnginesSection";

describe("EnginesSection", () => {
  it("lists the engines and checks again on demand", async () => {
    let installed = false;
    const fetchMock = mockRoutes({
      "GET /api/engines": () => json([engineStatus("kokoro", false)]),
      "GET /api/engines?refresh=true": () => {
        installed = true;
        return json([engineStatus("kokoro", true)]);
      },
    });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <EnginesSection />
      </QueryClientProvider>,
    );

    const row = (await screen.findByText("Engine kokoro")).closest("li")!;
    expect(within(row).getByText(/Not installed/)).toBeVisible();
    expect(within(row).getByRole("link", { name: "see setup" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Check again" }));

    expect(await screen.findByText("Installed 1.0")).toBeVisible();
    expect(installed).toBe(true);
    expect(callsTo(fetchMock, "GET", "/api/engines?refresh=true")).toHaveLength(
      1,
    );
  });
});
