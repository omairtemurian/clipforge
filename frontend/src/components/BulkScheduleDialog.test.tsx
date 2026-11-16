import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { callsTo, clip, json, mockRoutes, project } from "@/testing/mockApi";
import { post, socialAccount } from "@/testing/postFixtures";
import { BulkScheduleDialog } from "./BulkScheduleDialog";

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTS = [
  socialAccount({ id: 1, display_name: "Main channel" }),
  socialAccount({ id: 2, platform: "tiktok", display_name: "pizza.tok" }),
];

function renderDialog(onClose = vi.fn()) {
  const fetchMock = mockRoutes({
    "GET /api/accounts": () => json(ACCOUNTS),
    "GET /api/projects": () =>
      json([
        project({ id: 1, title: "Still going", status: "running" }),
        project({ id: 2, title: "Late show" }),
      ]),
    "GET /api/projects/2/clips": () =>
      json([
        clip({ id: 21, title: "Pizza night" }),
        clip({ id: 22, title: "Taxi ride" }),
      ]),
    "POST /api/posts/bulk-schedule": () =>
      json([post({ id: 31 }), post({ id: 32 })], 201),
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <BulkScheduleDialog onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, onClose };
}

describe("BulkScheduleDialog", () => {
  it("schedules every chosen clip to every account with each platform's text", async () => {
    const user = userEvent.setup();
    const { fetchMock, onClose } = renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Bulk schedule" });

    expect(
      await within(dialog).findByRole("combobox", { name: "Project" }),
    ).toHaveDisplayValue("Late show");
    await user.click(await within(dialog).findByLabelText("Select all"));
    expect(within(dialog).getByText("2 chosen")).toBeInTheDocument();
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "Choose an account to post to.",
    );

    await user.click(within(dialog).getByLabelText(/Main channel/));
    await user.click(within(dialog).getByLabelText(/pizza\.tok/));
    expect(within(dialog).getByRole("status")).toHaveTextContent(
      "Choose who can see the TikTok posts.",
    );
    const tabs = within(dialog).getByRole("tablist", { name: "Platforms" });
    expect(
      within(tabs)
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["YouTube", "TikTok"]);
    expect(within(dialog).getByLabelText("Title")).toHaveAttribute(
      "placeholder",
      "Each clip's own title",
    );
    await user.type(within(dialog).getByLabelText("Hashtags"), "#late");

    await user.click(within(tabs).getByRole("tab", { name: "TikTok" }));
    expect(within(dialog).queryByLabelText("Title")).not.toBeInTheDocument();
    await user.selectOptions(
      within(dialog).getByLabelText("Who can see it"),
      "PUBLIC_TO_EVERYONE",
    );
    await user.click(within(dialog).getByRole("button", { name: "Sat" }));
    await user.click(
      within(dialog).getByRole("button", { name: "Schedule 4 posts" }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [call] = callsTo(fetchMock, "POST", "/api/posts/bulk-schedule");
    const body = JSON.parse(String(call[1]?.body));
    expect(body).toMatchObject({
      clip_ids: [21, 22],
      queue: true,
      rules: { times: ["09:00", "18:00"], skip_days: ["sat"] },
      targets: [
        {
          account_id: 1,
          text: { title: null, caption: null, hashtags: ["late"] },
        },
        {
          account_id: 2,
          text: { caption: null, privacy: "PUBLIC_TO_EVERYONE" },
        },
      ],
    });
  });
});
