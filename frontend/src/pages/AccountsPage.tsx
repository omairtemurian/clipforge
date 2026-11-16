import { PlusIcon, UserIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useAccounts, useConnectAccount, usePlatforms } from "@/api/accounts";
import { AccountRow } from "@/components/accounts/AccountRow";
import { ConnectionsDialog } from "@/components/accounts/ConnectionsDialog";
import { DeveloperApps } from "@/components/accounts/DeveloperApps";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import {
  platformLabel,
  supportedPlatforms,
  type SocialPlatform,
} from "@/lib/platforms";
import { cn } from "@/lib/utils";
import { toast } from "@/lib/toast";
import { EmptyState } from "@/components/ui/empty-state";
import { pageColumn } from "@/lib/surfaces";

type Filter = SocialPlatform | "all";

interface Waiting {
  platform: SocialPlatform;
  known: number;
}

/** Social accounts: the accounts connected for publishing (filter by
 * platform, Remove), the "Social account connections" modal that starts a
 * platform's OAuth sign-in in a popup, and the state of each platform's
 * developer app. */
export function AccountsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [waiting, setWaiting] = useState<Waiting | null>(null);
  const [connected, setConnected] = useState<{
    platform: SocialPlatform;
  } | null>(null);
  const platforms = usePlatforms();
  const accounts = useAccounts(waiting !== null);
  const connect = useConnectAccount();
  const supported = supportedPlatforms(platforms.data);
  const count = accounts.data?.length ?? 0;

  // The sign-in finished in the other window once a new account shows up.
  if (waiting && count > waiting.known) {
    setConnected({ platform: waiting.platform });
    setWaiting(null);
    setDialogOpen(false);
  }

  useEffect(() => {
    if (connected) {
      toast.success(`${platformLabel(connected.platform)} account connected.`);
    }
  }, [connected]);

  function startConnect(platform: SocialPlatform) {
    connect.mutate(platform, {
      onSuccess: () => setWaiting({ platform, known: count }),
    });
  }

  const shown = (accounts.data ?? []).filter(
    (account) => filter === "all" || account.platform === filter,
  );

  return (
    <>
      <PageHeader
        title="Social accounts"
        description="Connect the YouTube, TikTok, Instagram and Facebook accounts that ClipForge publishes your clips to. Sign-ins use your own developer apps; tokens stay encrypted on this machine."
      />
      <div className={cn(pageColumn(), "flex flex-col gap-8 pb-10")}>
        <section
          aria-labelledby="accounts-list"
          className="flex flex-col gap-4"
        >
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="accounts-list" className="mr-auto text-section">
              Connected accounts
            </h2>
            <Button onClick={() => setDialogOpen(true)}>
              <PlusIcon aria-hidden />
              Add account
            </Button>
          </div>
          <div
            role="group"
            aria-label="Filter by platform"
            className="flex flex-wrap gap-2"
          >
            {(["all", ...supported.map((s) => s.platform)] as Filter[]).map(
              (option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={filter === option}
                  onClick={() => setFilter(option)}
                  className={cn(
                    "cursor-pointer rounded-full border px-3 py-1 text-body transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    filter === option
                      ? "border-primary bg-primary/15 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option === "all" ? "All" : platformLabel(option)}
                </button>
              ),
            )}
          </div>
          {accounts.isError && (
            <p role="alert" className="text-body text-destructive">
              Could not load the connected accounts.
            </p>
          )}
          {accounts.isSuccess && shown.length === 0 && (
            <EmptyState
              icon={UserIcon}
              className="py-8"
              title={
                filter === "all"
                  ? "No accounts connected yet"
                  : `No ${platformLabel(filter)} accounts connected yet`
              }
              action={
                filter === "all" ? (
                  <Button
                    variant="secondary"
                    onClick={() => setDialogOpen(true)}
                  >
                    Connect an account
                  </Button>
                ) : (
                  <Button variant="secondary" onClick={() => setFilter("all")}>
                    Show all accounts
                  </Button>
                )
              }
            >
              {filter === "all" && "Sign in to a platform to publish clips."}
            </EmptyState>
          )}
          {shown.length > 0 && (
            <ul aria-label="Connected accounts" className="flex flex-col gap-3">
              {shown.map((account) => (
                <AccountRow key={account.id} account={account} />
              ))}
            </ul>
          )}
        </section>
        <DeveloperApps platforms={supported} />
      </div>
      {dialogOpen && (
        <ConnectionsDialog
          platforms={supported}
          waitingFor={waiting?.platform ?? null}
          connecting={connect.isPending}
          onConnect={startConnect}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </>
  );
}
