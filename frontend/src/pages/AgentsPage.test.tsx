import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import type { AgentSetup, ApiKey, Webhook } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, json, mockRoutes } from "@/testing/mockApi";
import { AgentsPage } from "./AgentsPage";

const SETUP: AgentSetup = {
  api_url: "http://127.0.0.1:8000",
  project_dir: "/Users/me/clipforge",
  mcp_command: "uv",
  mcp_args: ["run", "--project", "/Users/me/clipforge", "clipforge-mcp"],
  docs_url: "http://127.0.0.1:8000/api/docs",
};
const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString();
const KEYS: ApiKey[] = [
  {
    id: 1,
    name: "Hermes",
    prefix: "cfk_HeRmEs",
    created_at: "2026-10-30T10:00:00Z",
    last_used_at: minutesAgo(5),
  },
  {
    id: 2,
    name: "n8n",
    prefix: "cfk_N8nN8n",
    created_at: "2026-10-31T10:00:00Z",
    last_used_at: null,
  },
];
const HOOK: Webhook = {
  id: 3,
  url: "http://localhost:5678/webhook/clipforge",
  events: ["post.published"],
  enabled: true,
  created_at: "2026-10-31T10:00:00Z",
};

function routes(extra: Parameters<typeof mockRoutes>[0] = {}) {
  return mockRoutes({
    "GET /api/api-keys": () => json(KEYS),
    "GET /api/agent-setup": () => json(SETUP),
    "GET /api/webhooks": () => json([HOOK]),
    ...extra,
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/settings/agents"]}>
        <AgentsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function bodyOf(call: unknown[]) {
  return JSON.parse((call[1] as RequestInit).body as string) as unknown;
}

afterEach(() => act(() => clearToasts()));

describe("AI agents & API page", () => {
  it("lists the keys with their last use and the agents seen lately", async () => {
    routes();
    renderPage();

    const list = await screen.findByRole("list", { name: "API keys" });
    expect(within(list).getByText(/Last used 5 min ago/)).toBeVisible();
    expect(within(list).getByText(/Never used/)).toBeVisible();
    expect(screen.getByText("Connected recently:")).toBeVisible();
    expect(screen.getByText("Hermes · 5 min ago")).toBeVisible();
    expect(screen.getByText(/only you can publish/)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open API docs (/api/docs)" }),
    ).toHaveAttribute("href", SETUP.docs_url);
  });

  it("shows a new key once, fills it into the MCP configs and copies it", async () => {
    const user = userEvent.setup();
    const writeText = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue();
    const created = { ...KEYS[1]!, id: 9, name: "Claude", key: "cfk_SECRET" };
    const fetchMock = routes({
      "POST /api/api-keys": () => json(created, 201),
    });
    renderPage();

    const hermes = await screen.findByLabelText("Add with the Hermes CLI");
    expect(hermes).toHaveTextContent("CLIPFORGE_API_KEY=cfk_YOUR_KEY");
    await user.type(screen.getByLabelText("Key name"), "Claude");
    await user.click(screen.getByRole("button", { name: "Create key" }));

    expect(bodyOf(callsTo(fetchMock, "POST", "/api/api-keys")[0]!)).toEqual({
      name: "Claude",
    });
    expect(await screen.findByText(/shown only once/)).toBeVisible();
    expect(hermes).toHaveTextContent("CLIPFORGE_API_KEY=cfk_SECRET");
    await user.click(
      screen.getByRole("button", { name: 'Copy API key "Claude"' }),
    );
    expect(writeText).toHaveBeenCalledWith("cfk_SECRET");
    expect(await screen.findByText("Copied")).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Claude Desktop" }));
    const config = screen.getByLabelText("claude_desktop_config.json");
    expect(JSON.parse(config.textContent ?? "")).toEqual({
      mcpServers: {
        clipforge: {
          command: "uv",
          args: SETUP.mcp_args,
          env: { CLIPFORGE_API_KEY: "cfk_SECRET" },
        },
      },
    });

    await user.click(screen.getByRole("button", { name: /hide it/ }));
    expect(screen.queryByText("cfk_SECRET")).toBeNull();
    expect(document.body.innerHTML).not.toContain("cfk_SECRET");
  });

  it("revokes a key after a confirmation", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "DELETE /api/api-keys/2": () => new Response(null, { status: 204 }),
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Revoke n8n" }));
    await user.click(screen.getByRole("button", { name: "Revoke n8n" }));

    expect(callsTo(fetchMock, "DELETE", "/api/api-keys/2")).toHaveLength(1);
  });

  it("adds a webhook for the chosen events and shows its secret once", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/webhooks": () =>
        json({ ...HOOK, id: 4, secret: "whsec_SECRET" }, 201),
      "DELETE /api/webhooks/3": () => new Response(null, { status: 204 }),
    });
    renderPage();

    expect(await screen.findByText(HOOK.url)).toBeVisible();
    await user.type(
      screen.getByLabelText("Webhook URL"),
      "https://hooks.example.com/cf",
    );
    await user.click(screen.getByLabelText("Clip rendered"));
    await user.click(screen.getByLabelText("Project processed"));
    await user.click(screen.getByRole("button", { name: "Add webhook" }));

    expect(bodyOf(callsTo(fetchMock, "POST", "/api/webhooks")[0]!)).toEqual({
      url: "https://hooks.example.com/cf",
      events: ["post.published", "post.failed"],
    });
    expect(await screen.findByLabelText("Webhook secret")).toHaveTextContent(
      "whsec_SECRET",
    );

    await user.click(
      screen.getByRole("button", { name: `Delete webhook ${HOOK.url}` }),
    );
    expect(callsTo(fetchMock, "DELETE", "/api/webhooks/3")).toHaveLength(1);
  });
});
