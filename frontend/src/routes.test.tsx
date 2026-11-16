import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "./api/queryClient";
import { AppRoutes } from "./routes";
import { project, SAVED_SETTINGS, usageSummary } from "./testing/mockApi";

const BODIES: Record<string, string> = {
  "/api/settings": JSON.stringify(SAVED_SETTINGS),
  "/api/usage": JSON.stringify(usageSummary()),
  "/api/agent-setup": JSON.stringify({
    api_url: "http://127.0.0.1:8000",
    project_dir: "/clipforge",
    mcp_command: "uv",
    mcp_args: ["run", "--project", "/clipforge", "clipforge-mcp"],
    docs_url: "http://127.0.0.1:8000/api/docs",
  }),
  "/api/storage": JSON.stringify({
    projects: [],
    total_bytes: 0,
    free_bytes: 0,
    data_dir: "/data",
  }),
  "/api/projects/7": JSON.stringify(
    project({ id: 7, title: "Interview cut", status: "done" }),
  ),
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => Promise.resolve(new Response(BODIES[url] ?? "[]"))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("app shell", () => {
  it("renders the 12 navigation links", () => {
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    const publish = screen.getByRole("navigation", {
      name: "Post navigation",
    });
    const labels = [
      ...within(nav).getAllByRole("link"),
      ...within(publish).getAllByRole("link"),
      screen.getByRole("link", { name: "Settings" }),
    ].map((link) => link.getAttribute("aria-label"));

    expect(labels).toEqual([
      "Home",
      "Projects",
      "Media library",
      "Collections",
      "Brand templates",
      "Watchlist",
      "Campaigns",
      "Approval inbox",
      "Ready to submit",
      "Calendar",
      "Post history",
      "Social accounts",
      "Settings",
    ]);
    expect(screen.getByRole("link", { name: "ClipForge home" })).toBeVisible();
  });

  it("navigates between pages and shows the breadcrumb on inner pages", async () => {
    const user = userEvent.setup();
    renderAt("/");

    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Projects" }));

    expect(
      screen.getByRole("heading", { name: "Projects" }),
    ).toBeInTheDocument();
    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByText("Projects")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("opens the Approval inbox from the Post group", async () => {
    const user = userEvent.setup();
    renderAt("/");

    await user.click(screen.getByRole("link", { name: "Approval inbox" }));

    expect(
      screen.getByRole("heading", { name: "Approval inbox" }),
    ).toBeInTheDocument();
    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByText("Approval inbox")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await screen.findByText("Nothing to approve")).toBeVisible();
  });

  it("opens Ready to submit from the Post group", async () => {
    const user = userEvent.setup();
    renderAt("/");

    await user.click(screen.getByRole("link", { name: "Ready to submit" }));

    expect(
      screen.getByRole("heading", { name: "Ready to submit" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Nothing to submit")).toBeVisible();
  });

  it("names a project by its title in the breadcrumb", async () => {
    renderAt("/projects/7");

    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByRole("link", { name: "Projects" })).toBeVisible();
    expect(await within(crumb).findByText("Interview cut")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it.each([
    ["/brand-templates", "Brand templates"],
    ["/watchlist", "Watchlist"],
    ["/campaigns", "Campaigns"],
    ["/calendar", "Calendar"],
    ["/post-history", "Post history"],
    ["/accounts", "Social accounts"],
    ["/auto-import", "Watchlist"],
    ["/settings", "Settings"],
    ["/library", "Media library"],
    ["/collections", "Collections"],
    ["/settings/storage", "Storage"],
  ])("renders %s", (path, heading) => {
    renderAt(path);
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("reaches AI agents & API from the Settings tabs", async () => {
    const user = userEvent.setup();
    renderAt("/settings");

    const tabs = screen.getByRole("navigation", { name: "Settings pages" });
    await user.click(
      within(tabs).getByRole("link", { name: "AI agents & API" }),
    );

    expect(
      screen.getByRole("heading", { name: "AI agents & API" }),
    ).toBeInTheDocument();
    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByRole("link", { name: "Settings" })).toBeVisible();
    expect(within(crumb).getByText("AI agents & API")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("sends an unknown path to Home", () => {
    renderAt("/nowhere");
    expect(
      screen.getByRole("heading", { name: "ClipForge" }),
    ).toBeInTheDocument();
  });

  it("collapses the sidebar to icons", async () => {
    const user = userEvent.setup();
    renderAt("/");

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(screen.queryByText("Create")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Projects" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeVisible();
  });

  it("focuses the search field with cmd+K and searches the Library", async () => {
    const user = userEvent.setup();
    renderAt("/settings");
    const search = screen.getByRole("searchbox");

    await user.keyboard("{Meta>}k{/Meta}");
    expect(search).toHaveFocus();

    await user.type(search, "funny bit{Enter}");
    expect(
      screen.getByRole("heading", { name: "Media library" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("searchbox", { name: "Search transcripts" }),
    ).toHaveValue("funny bit");
  });
});
