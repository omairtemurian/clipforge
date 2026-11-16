import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { AppearanceSection } from "@/components/appsettings/AppearanceSection";
import { THEME_KEY } from "@/lib/theme";
import { Sidebar } from "./Sidebar";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response("[]"))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.className = "";
});

function renderBoth() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/projects"]}>
        <Sidebar collapsed={false} onToggle={() => {}} />
        <AppearanceSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("theme switches", () => {
  it("start on Light and flip together from the sidebar's sun/moon button", async () => {
    renderBoth();
    expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();

    await userEvent.click(
      screen.getByRole("button", { name: "Switch to dark theme" }),
    );

    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
    expect(
      screen.getByRole("button", { name: "Switch to light theme" }),
    ).toBeInTheDocument();
  });

  it("save System from Settings -> Appearance and follow the OS", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    renderBoth();

    await userEvent.click(screen.getByRole("radio", { name: "System" }));

    expect(localStorage.getItem(THEME_KEY)).toBe("system");
    expect(screen.getByRole("radio", { name: "System" })).toBeChecked();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("mark the active nav link with a filled icon in a tile", () => {
    renderBoth();
    const active = screen.getByRole("link", { name: "Projects" });
    expect(active).toHaveClass("font-semibold");
    expect(active.querySelector("span")).toHaveClass("bg-sidebar-accent");
    expect(
      screen.getByRole("link", { name: "Home" }).querySelector("span"),
    ).not.toHaveClass("bg-sidebar-accent");
  });
});
