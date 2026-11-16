import { FilmSlateIcon, SparkleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import {
  useBrollOps,
  useBrollProviders,
  useBrollSpots,
  type BrollOp,
} from "@/api/broll";
import { useMediaLibrary } from "@/api/mediaLibrary";
import type { BrollSpot, Clip, StockClip, TrackItem } from "@/api/types";
import { PlacedBroll } from "@/components/broll/PlacedBroll";
import { SpotCard } from "@/components/broll/SpotCard";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { stockSource } from "@/lib/broll";

interface BrollPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
  /** The timeline's selected layer item, and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

type Mode = "cutaway" | "pip";

const SPOT_COUNTS = [2, 3, 4, 6, 8];

/**
 * The editor's B-roll panel (SPEC-v2 3.6): "Find B-roll spots" has the AI
 * pick the sentences of the saved clip that stock footage helps and search
 * a stock provider (Pexels, Pixabay) for each. Every spot shows its
 * thumbnails with attribution and license; choosing one puts it on the
 * B-roll track at the spot as a full-screen cutaway or a
 * picture-in-picture, or replaces the B-roll already there. The B-roll on
 * the clip is listed with "Remove". The spots are not saved (find them
 * again to get new ones) and, like every change here, act on the saved
 * clip, so they wait for unsaved changes. Render the clip again to see
 * the B-roll in the video.
 */
export function BrollPanel({
  clip,
  edits,
  busy,
  selectedItem,
  onSelectItem,
}: BrollPanelProps) {
  const providers = useBrollProviders();
  const library = useMediaLibrary();
  const find = useBrollSpots(clip.id);
  const ops = useBrollOps(clip.id);
  const [mode, setMode] = useState<Mode>("cutaway");
  const [count, setCount] = useState(4);
  const [provider, setProvider] = useState("");
  const [spots, setSpots] = useState<BrollSpot[] | null>(null);
  const waiting = edits.dirty || busy;
  const locked = waiting || find.isPending || ops.isPending;
  const enabled = (providers.data ?? []).filter((each) => each.enabled);
  const disabledMessage = (providers.data ?? []).find(
    (each) => !each.enabled,
  )?.message;
  const items = edits.layers.broll;

  const search = async () => {
    try {
      setSpots(
        await find.mutateAsync({
          max_spots: count,
          mode,
          provider: (provider || null) as "pexels" | "pixabay" | null,
        }),
      );
    } catch {
      // apiFetch has shown the error
    }
  };
  const apply = async (op: BrollOp) => {
    try {
      edits.reset(await ops.mutateAsync(op));
    } catch {
      // apiFetch has shown the error
    }
  };
  const choose = (spot: BrollSpot, stock: StockClip, replace?: TrackItem) =>
    apply(
      replace
        ? { type: "replace", itemId: replace.id, source: stockSource(stock) }
        : {
            type: "insert",
            body: {
              ...stockSource(stock),
              start: spot.start,
              end: spot.end,
              mode,
              x: 0.5,
              y: 0.3,
              width: 0.8,
            },
          },
    );

  return (
    <div className="flex flex-col gap-5">
      {waiting && (
        <p role="status" className="text-caption text-muted-foreground">
          B-roll waits until your changes are saved.
        </p>
      )}
      <PanelGroup title="Find B-roll">
        {providers.isSuccess && enabled.length === 0 ? (
          <EmptyState
            icon={FilmSlateIcon}
            title="No stock provider"
            className="py-8"
          >
            {disabledMessage ??
              "Set PEXELS_API_KEY or PIXABAY_API_KEY in .env to search stock video."}
          </EmptyState>
        ) : (
          <>
            <Field label="Show as">
              <NativeSelect
                block
                aria-label="Show as"
                value={mode}
                onChange={(event) => setMode(event.target.value as Mode)}
              >
                <option value="cutaway">Full-screen cutaway</option>
                <option value="pip">Picture-in-picture</option>
              </NativeSelect>
            </Field>
            <Field label="Most spots">
              <NativeSelect
                block
                aria-label="Most spots"
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
              >
                {SPOT_COUNTS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {enabled.length > 1 && (
              <Field label="Stock provider">
                <NativeSelect
                  block
                  aria-label="Stock provider"
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  <option value="">Any</option>
                  {enabled.map((each) => (
                    <option key={each.provider} value={each.provider}>
                      {each.label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            )}
            <Button
              disabled={locked || !providers.isSuccess}
              onClick={() => void search()}
            >
              <SparkleIcon />
              {spots ? "Find new spots" : "Find B-roll spots"}
            </Button>
          </>
        )}
        {find.isPending && (
          <p role="status" className="text-caption text-muted-foreground">
            Looking for spots and stock video…
          </p>
        )}
      </PanelGroup>
      {spots && (
        <PanelGroup title="Suggested spots">
          {spots.length === 0 ? (
            <p className="text-caption text-muted-foreground">
              The AI found no sentence that B-roll helps.
            </p>
          ) : (
            <ul aria-label="B-roll spots" className="flex flex-col gap-3">
              {spots.map((spot) => (
                <SpotCard
                  key={spot.sentence}
                  spot={spot}
                  items={items}
                  disabled={locked}
                  onChoose={(...args) => void choose(...args)}
                  onSkip={(skipped) =>
                    setSpots(spots.filter((each) => each !== skipped))
                  }
                />
              ))}
            </ul>
          )}
        </PanelGroup>
      )}
      <PanelGroup title="B-roll on the clip">
        {items.length === 0 ? (
          <p className="text-caption text-muted-foreground">
            No B-roll yet. Choose a stock video for a spot.
          </p>
        ) : (
          <PlacedBroll
            items={items}
            library={library.data ?? []}
            selectedItem={selectedItem}
            disabled={locked}
            onSelect={onSelectItem}
            onRemove={(item) => void apply({ type: "remove", itemId: item.id })}
          />
        )}
      </PanelGroup>
      <p className="text-caption text-muted-foreground">
        Render the clip again to see the B-roll.
      </p>
    </div>
  );
}
