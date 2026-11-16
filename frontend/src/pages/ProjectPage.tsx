import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useOpenProject, useProject } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isNew } from "@/lib/projectStatus";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import { Gallery } from "./Gallery";
import { Processing } from "./Processing";

/** One project: the processing view until it is done, then its clips. */
export function ProjectPage() {
  const id = Number(useParams().projectId);
  const project = useProject(id);
  const open = useOpenProject();
  const unopened = project.data !== undefined && isNew(project.data);
  const { mutate } = open;
  useEffect(() => {
    if (unopened) mutate(id);
  }, [unopened, id, mutate]);

  if (project.isPending) {
    return (
      <div className={cn(pageColumn("wide"), "pt-8")}>
        <Skeleton className="h-8 w-1/3 rounded-lg" />
        <Skeleton className="mt-2 h-4 w-40" />
      </div>
    );
  }
  if (project.isError) {
    return (
      <div
        className={cn(
          pageColumn(),
          "flex flex-col items-start gap-4 pt-section text-body text-muted-foreground",
        )}
      >
        <p>Could not load this project.</p>
        <Button variant="outline" asChild>
          <Link to="/">Back to Home</Link>
        </Button>
      </div>
    );
  }

  const data = project.data;
  if (data.status !== "done") return <Processing project={data} />;

  return <Gallery project={data} />;
}
