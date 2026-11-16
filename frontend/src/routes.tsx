import { Navigate, Route, Routes } from "react-router-dom";
import { AccountsPage } from "@/pages/AccountsPage";
import { AgentsPage } from "@/pages/AgentsPage";
import { ApprovalInboxPage } from "@/pages/ApprovalInboxPage";
import { ReadyToSubmitPage } from "@/pages/ReadyToSubmitPage";
import { AppShell } from "@/components/AppShell";
import { BrandTemplatesPage } from "@/pages/BrandTemplatesPage";
import { CalendarPage } from "@/pages/CalendarPage";
import { CampaignsPage } from "@/pages/CampaignsPage";
import { CollectionsPage } from "@/pages/CollectionsPage";
import { EditorPage } from "@/pages/Editor";
import {
  PRO_EDIT_ROUTE,
  ProEditRoute,
  STYLE_RECIPES_ROUTE,
  StyleRecipesRoute,
} from "@/features/proedit";
import { HomePage } from "@/pages/HomePage";
import { LibraryPage } from "@/pages/LibraryPage";
import { PostHistoryPage } from "@/pages/PostHistoryPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { StoragePage } from "@/pages/StoragePage";
import { WatchlistPage } from "@/pages/Watchlist";

/** The routes of the app (the clip editor is full screen, outside the
 * shell; a clip's Pro Edit page shows only while Pro Edit is enabled); the
 * old /auto-import goes to the Watchlist, an unknown path to Home. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="clips/:clipId" element={<EditorPage />} />
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route path={PRO_EDIT_ROUTE} element={<ProEditRoute />} />
        <Route path={STYLE_RECIPES_ROUTE} element={<StyleRecipesRoute />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="collections" element={<CollectionsPage />} />
        <Route path="brand-templates" element={<BrandTemplatesPage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route
          path="auto-import"
          element={<Navigate to="/watchlist" replace />}
        />
        <Route path="campaigns" element={<CampaignsPage />} />
        <Route path="inbox" element={<ApprovalInboxPage />} />
        <Route path="submit" element={<ReadyToSubmitPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="post-history" element={<PostHistoryPage />} />
        <Route path="accounts" element={<AccountsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/agents" element={<AgentsPage />} />
        <Route path="settings/storage" element={<StoragePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
