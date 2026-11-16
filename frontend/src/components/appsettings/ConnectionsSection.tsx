import { Link } from "react-router-dom";
import { useAccounts, usePlatforms } from "@/api/accounts";
import { Pill } from "@/components/ui/pill";
import { platformLabel, supportedPlatforms } from "@/lib/platforms";
import { Section } from "./Section";

/** The platforms ClipForge can publish to: how many of your accounts are
 * connected and whether the developer app keys are set. Sign-ins happen on
 * the Social accounts page. */
export function ConnectionsSection() {
  const platforms = usePlatforms();
  const accounts = useAccounts();
  const error = platforms.isError || accounts.isError;
  const counts = new Map<string, number>();
  for (const account of accounts.data ?? []) {
    counts.set(account.platform, (counts.get(account.platform) ?? 0) + 1);
  }
  return (
    <Section
      title="Platform connections"
      description="The social accounts that ClipForge publishes your clips to."
    >
      {error && (
        <p role="alert" className="text-body text-destructive">
          Could not load the connections.
        </p>
      )}
      <ul className="flex flex-col divide-y divide-border">
        {supportedPlatforms(platforms.data).map((status) => {
          const count = counts.get(status.platform) ?? 0;
          return (
            <li
              key={status.platform}
              className="flex items-center justify-between gap-4 py-2 text-body"
            >
              <span className="font-medium">
                {platformLabel(status.platform)}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-muted-foreground">
                  {count === 1 ? "1 account" : `${count} accounts`}
                </span>
                <Pill tone={status.configured ? "success" : "warning"}>
                  {status.configured ? "App keys set" : "App keys missing"}
                </Pill>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-body text-muted-foreground">
        <Link
          to="/accounts"
          className="text-primary-ink underline underline-offset-2"
        >
          Manage social accounts
        </Link>{" "}
        to sign in or remove an account.
      </p>
    </Section>
  );
}
