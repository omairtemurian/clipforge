import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import type { BrandTemplate } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, json, mockRoutes } from "@/testing/mockApi";
import { BrandTemplatesPage } from "./BrandTemplatesPage";

const ACME: BrandTemplate = {
  id: 1,
  name: "Acme",
  logo_path: "/data/brand/1/logo.png",
  logo_position: "br",
  logo_opacity: 0.8,
  font: "Inter Bold",
  primary_color: "#FF6B35",
  intro_path: null,
  outro_path: "/data/brand/1/outro.mp4",
};

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <BrandTemplatesPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function routes(
  templates: BrandTemplate[],
  extra: Parameters<typeof mockRoutes>[0] = {},
) {
  return mockRoutes({
    "GET /api/brand-templates": () => json(templates),
    "GET /api/brand-fonts": () => json(["Inter", "Inter Bold"]),
    ...extra,
  });
}

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:logo"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Brand templates page", () => {
  it("opens the new template form when there are no templates", async () => {
    routes([]);
    renderPage();

    expect(
      await screen.findByRole("form", { name: "New brand template" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create template" }),
    ).toBeVisible();
    expect(
      screen.getByRole("list", { name: "Brand templates" }).children,
    ).toHaveLength(0);
  });

  it("lists the templates and edits the first with its saved files", async () => {
    routes([ACME, { ...ACME, id: 2, name: "Beta" }]);
    renderPage();

    const form = await screen.findByRole("form", { name: "Edit Acme" });
    expect(within(form).getByLabelText("Name")).toHaveValue("Acme");
    expect(within(form).getByText("logo.png")).toBeVisible();
    expect(within(form).getByText("outro.mp4")).toBeVisible();
    expect(within(form).getByAltText("Logo preview")).toHaveAttribute(
      "src",
      expect.stringContaining("/api/brand-templates/1/logo"),
    );
    const list = screen.getByRole("list", { name: "Brand templates" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);

    await userEvent.click(within(list).getByRole("button", { name: /Beta/ }));
    expect(
      await screen.findByRole("form", { name: "Edit Beta" }),
    ).toBeInTheDocument();
  });

  it("shows the validation problems and sends nothing", async () => {
    const fetchMock = routes([]);
    renderPage();
    await screen.findByRole("form", { name: "New brand template" });

    await userEvent.click(
      screen.getByRole("button", { name: "Create template" }),
    );

    expect(screen.getByText("Give the template a name.")).toBeVisible();
    expect(screen.getByText("Choose a logo image.")).toBeVisible();
    expect(callsTo(fetchMock, "POST", "/api/brand-templates")).toHaveLength(0);
  });

  it("moves the logo in the preview with the position chips", async () => {
    routes([ACME]);
    renderPage();
    const form = await screen.findByRole("form", { name: "Edit Acme" });
    expect(within(form).getByAltText("Logo preview")).toHaveAttribute(
      "data-position",
      "br",
    );

    await userEvent.click(
      within(form).getByRole("radio", { name: "Top left" }),
    );

    expect(within(form).getByAltText("Logo preview")).toHaveAttribute(
      "data-position",
      "tl",
    );
  });

  it("creates a template from the form and selects it", async () => {
    const saved = { ...ACME, id: 5, name: "Fresh" };
    const fetchMock = routes([], {
      "POST /api/brand-templates": () => json(saved, 201),
    });
    renderPage();
    await screen.findByRole("form", { name: "New brand template" });

    await userEvent.type(screen.getByLabelText("Name"), "Fresh");
    await userEvent.upload(
      screen.getByLabelText("Logo", { selector: "input" }),
      new File(["x"], "mark.png", { type: "image/png" }),
    );
    expect(screen.getByAltText("Logo preview")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Create template" }),
    );

    const [call] = callsTo(fetchMock, "POST", "/api/brand-templates");
    const body = call[1]?.body as FormData;
    expect(body.get("name")).toBe("Fresh");
    expect((body.get("logo") as File).name).toBe("mark.png");
    expect(await screen.findByText('Saved "Fresh".')).toBeVisible();
  });

  it("saves a change with PUT and drops the outro", async () => {
    const fetchMock = routes([ACME], {
      "PUT /api/brand-templates/1": () => json({ ...ACME, outro_path: null }),
    });
    renderPage();
    const form = await screen.findByRole("form", { name: "Edit Acme" });

    await userEvent.click(
      within(form).getByRole("button", { name: "Remove outro video" }),
    );
    expect(within(form).queryByText("outro.mp4")).not.toBeInTheDocument();
    await userEvent.click(
      within(form).getByRole("button", { name: "Save changes" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "PUT", "/api/brand-templates/1")).toHaveLength(
        1,
      ),
    );
    const body = callsTo(fetchMock, "PUT", "/api/brand-templates/1")[0][1]
      ?.body as FormData;
    expect(body.get("remove_outro")).toBe("true");
    expect(body.has("logo")).toBe(false);
  });

  it("asks before it deletes a template", async () => {
    const fetchMock = routes([ACME], {
      "DELETE /api/brand-templates/1": () =>
        new Response(null, { status: 204 }),
    });
    renderPage();
    const form = await screen.findByRole("form", { name: "Edit Acme" });

    await userEvent.click(within(form).getByRole("button", { name: "Delete" }));
    expect(callsTo(fetchMock, "DELETE", "/api/brand-templates/1")).toHaveLength(
      0,
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Confirm delete" }),
    );

    expect(await screen.findByText("Template deleted.")).toBeVisible();
    expect(callsTo(fetchMock, "DELETE", "/api/brand-templates/1")).toHaveLength(
      1,
    );
  });
});
