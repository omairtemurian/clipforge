import { useLocation, useSearchParams } from "react-router-dom";
import { FoldersIcon } from "@phosphor-icons/react";
import { PageHeader } from "@/components/PageHeader";
import { CollectionList } from "@/components/collections/CollectionList";
import { CollectionPanel } from "@/components/collections/CollectionPanel";
import { EmptyState } from "@/components/ui/empty-state";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** The clips whose renders the page that opened this one queued. */
function queuedOf(state: unknown): number[] {
  if (typeof state !== "object" || state === null || !("queued" in state)) {
    return [];
  }
  const { queued } = state;
  return Array.isArray(queued)
    ? queued.filter((id): id is number => typeof id === "number")
    : [];
}

/**
 * Collections of clips from any project (?id= is the one open): make,
 * rename and delete them, render their clips and download them as a zip.
 */
export function CollectionsPage() {
  const [params, setParams] = useSearchParams();
  const { state } = useLocation();
  const raw = params.get("id");
  const selectedId = raw ? Number(raw) : null;

  function select(id: number | null) {
    setParams(id === null ? {} : { id: String(id) }, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Collections"
        width="wide"
        description="Group clips from any project and export them together."
      />
      <div
        className={cn(
          pageColumn("wide"),
          "grid items-start gap-8 pb-section md:grid-cols-[18rem_minmax(0,1fr)]",
        )}
      >
        <CollectionList selectedId={selectedId} onSelect={select} />
        {selectedId === null ? (
          <EmptyState icon={FoldersIcon} title="Pick a collection">
            Its clips, their status and the zip of the rendered ones show here.
          </EmptyState>
        ) : (
          <CollectionPanel
            key={selectedId}
            id={selectedId}
            queued={queuedOf(state)}
            onDeleted={() => select(null)}
          />
        )}
      </div>
    </>
  );
}
