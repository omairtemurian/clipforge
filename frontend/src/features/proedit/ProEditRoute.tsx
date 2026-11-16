import { ArrowLeftIcon, MagicWandIcon } from "@phosphor-icons/react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useClip } from "@/api/clips";
import type { Clip } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import { useProEditEnabled, useProEditVariants } from "./api";
import { proEditPath } from "./paths";
import { ProEditEditor } from "./ProEditEditor";

function Loading() {
  return (
    <div className={cn(pageColumn(), "flex flex-col gap-4 pt-section")}>
      <Skeleton className="h-8 w-1/3 rounded-lg" />
      <Skeleton className="h-24 rounded-xl" />
    </div>
  );
}

/** The editor of the Pro Edit variants of original, or why there are
 * none. */
function Variants({ original }: { original: Clip }) {
  const variants = useProEditVariants(original.id);
  if (variants.isPending) return <Skeleton className="h-24 rounded-xl" />;
  if (variants.isError) {
    return (
      <p className="text-body text-muted-foreground">
        Could not load the Pro Edit variants.
      </p>
    );
  }
  if (variants.data.length === 0) {
    return (
      <EmptyState icon={MagicWandIcon} title="No Pro Edit variant yet">
        A Pro Edit variant is a new clip next to this one; this clip and its
        video stay as they are.
      </EmptyState>
    );
  }
  return <ProEditEditor original={original} variants={variants.data} />;
}

/** The Pro Edit page of a loaded original clip: the editor of its
 * variants, and the way back to the original in the editor. */
function ProEditPage({ clip }: { clip: Clip }) {
  return (
    <>
      <PageHeader
        title="Pro Edit"
        width="wide"
        description={`Compare and edit the Pro Edit of “${clip.title}”.`}
        actions={
          <Button variant="outline" asChild>
            <Link to={`/clips/${clip.id}`}>
              <ArrowLeftIcon aria-hidden />
              Back to the clip
            </Link>
          </Button>
        }
      />
      <div className={cn(pageColumn("wide"), "pb-section")}>
        <Variants original={clip} />
      </div>
    </>
  );
}

/** The route /clips/:clipId/proedit, registered behind the Pro Edit flag:
 * while Pro Edit is off it goes to the clip's editor instead; for a
 * variant it goes to its original's page with the variant chosen. */
export function ProEditRoute() {
  const id = Number(useParams().clipId);
  const proEdit = useProEditEnabled();
  const clip = useClip(id);
  if (proEdit.pending) return <Loading />;
  if (!proEdit.enabled) return <Navigate to={`/clips/${id}`} replace />;
  if (clip.isPending) return <Loading />;
  if (clip.isError) {
    return (
      <div className={cn(pageColumn(), "pt-section")}>
        <p className="text-body text-muted-foreground">
          Could not load this clip.
        </p>
      </div>
    );
  }
  const parent = clip.data.parent_clip_id;
  if (clip.data.variant === "pro_edit" && parent !== null) {
    return <Navigate to={proEditPath(parent, id)} replace />;
  }
  return <ProEditPage clip={clip.data} />;
}
