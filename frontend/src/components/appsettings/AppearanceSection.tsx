import { DesktopIcon, MoonIcon, SunIcon } from "@phosphor-icons/react";
import { RadioGroup } from "radix-ui";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { useTheme } from "@/hooks/useTheme";
import type { ThemeChoice } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Section } from "./Section";

const CHOICES: { value: ThemeChoice; label: string; icon: PhosphorIcon }[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: DesktopIcon },
];

/**
 * The color theme of this browser: Light, Dark or System (follows the OS).
 * Saved in the browser right away, not with the settings form.
 */
export function AppearanceSection() {
  const { choice, setChoice } = useTheme();
  return (
    <Section
      title="Appearance"
      description="The color theme of ClipForge in this browser."
    >
      <RadioGroup.Root
        value={choice}
        onValueChange={(value) => setChoice(value as ThemeChoice)}
        aria-label="Theme"
        orientation="horizontal"
        className="inline-flex w-fit gap-1 rounded-full bg-muted p-1"
      >
        {CHOICES.map(({ value, label, icon: Icon }) => {
          const checked = choice === value;
          return (
            <RadioGroup.Item
              key={value}
              value={value}
              className={cn(
                "flex h-8 cursor-pointer items-center gap-2 rounded-full px-4 text-body font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                checked
                  ? "bg-card text-foreground shadow-card"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon
                aria-hidden
                weight={checked ? "fill" : "regular"}
                className="size-4"
              />
              {label}
            </RadioGroup.Item>
          );
        })}
      </RadioGroup.Root>
    </Section>
  );
}
