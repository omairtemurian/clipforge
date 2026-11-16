import { useAppSettings } from "@/api/appSettings";
import { PageHeader } from "@/components/PageHeader";
import { AppearanceSection } from "@/components/appsettings/AppearanceSection";
import { ConnectionsSection } from "@/components/appsettings/ConnectionsSection";
import { EnginesSection } from "@/components/appsettings/EnginesSection";
import { NewProjectDefaults } from "@/components/appsettings/NewProjectDefaults";
import { NotificationsSection } from "@/components/appsettings/NotificationsSection";
import { SettingsForm } from "@/components/appsettings/SettingsForm";
import { SettingsTabs } from "@/components/appsettings/SettingsTabs";
import { UsageSection } from "@/components/appsettings/UsageSection";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** Settings: the color theme (Appearance), the language model and API keys
 * (with a connection test), transcription, credit line, tool and storage
 * paths and posting, saved through /api/settings; the speech language of new
 * projects; the platform connections; notifications (email, desktop); the
 * usage of the month with its caps; and the install state of the engines. */
export function SettingsPage() {
  const settings = useAppSettings();
  return (
    <>
      <PageHeader
        title="Settings"
        description="Language models, API keys, connections, notifications and defaults for new projects."
      />
      <div className={cn(pageColumn(), "flex flex-col gap-6 pb-10")}>
        <div className="max-w-2xl">
          <SettingsTabs />
        </div>
        <div className="max-w-2xl">
          <AppearanceSection />
        </div>
        {settings.isError && (
          <p role="alert" className="text-body text-destructive">
            Could not load the settings.
          </p>
        )}
        {settings.data && (
          <div className="flex max-w-2xl flex-col gap-6">
            <SettingsForm saved={settings.data} />
            <NewProjectDefaults />
            <ConnectionsSection />
            <NotificationsSection saved={settings.data} />
            <UsageSection saved={settings.data} />
            <EnginesSection />
          </div>
        )}
      </div>
    </>
  );
}
