import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { engineStatus, json, mockRoutes } from "@/testing/mockApi";
import { EngineGate } from "./EngineGate";

function renderGate(engine: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <EngineGate engine={engine}>
        <button type="button">Make voiceover</button>
      </EngineGate>
    </QueryClientProvider>,
  );
}

describe("EngineGate", () => {
  it("shows its children when the engine is installed", async () => {
    mockRoutes({
      "GET /api/engines": () =>
        json([engineStatus("kokoro", true), engineStatus("piper", false)]),
    });
    renderGate("kokoro");

    expect(
      await screen.findByRole("button", { name: "Make voiceover" }),
    ).toBeVisible();
    expect(screen.queryByText(/Not installed/)).not.toBeInTheDocument();
  });

  it("says not installed and links to the setup when it is not", async () => {
    mockRoutes({
      "GET /api/engines": () =>
        json([engineStatus("kokoro", true), engineStatus("piper", false)]),
    });
    renderGate("piper");

    expect(await screen.findByText(/Not installed/)).toBeVisible();
    expect(screen.getByRole("link", { name: "see setup" })).toHaveAttribute(
      "href",
      "https://github.com/omairtemurian/clipforge#engine-piper",
    );
    expect(
      screen.queryByRole("button", { name: "Make voiceover" }),
    ).not.toBeInTheDocument();
  });

  it("says so when the server does not know the engine", async () => {
    mockRoutes({ "GET /api/engines": () => json([]) });
    renderGate("kokoro");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Could not check whether kokoro is installed.",
    );
  });
});
