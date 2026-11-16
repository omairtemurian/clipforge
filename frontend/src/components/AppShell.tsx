import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useWatchAlerts } from "@/hooks/useWatchAlerts";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/** Page frame: collapsible sidebar, top bar (inner pages only) and the
 * page; alerts on new uploads and go-lives of watched creators. */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  useWatchAlerts();
  const { pathname } = useLocation();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        {pathname !== "/" && <TopBar />}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
