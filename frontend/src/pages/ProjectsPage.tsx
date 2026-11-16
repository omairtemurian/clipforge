import { PlusIcon } from "@phosphor-icons/react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { pageColumn } from "@/lib/surfaces";
import { ProjectGrid } from "@/components/ProjectGrid";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Button } from "@/components/ui/button";
import {
  PROJECT_FILTERS,
  filterProjects,
  matchProjects,
  type ProjectFilter,
} from "@/lib/projectStatus";
import { cn } from "@/lib/utils";

function statusOf(value: string | null): ProjectFilter {
  return (
    PROJECT_FILTERS.find((filter) => filter.value === value)?.value ?? "all"
  );
}

/** What the grid says when the filters keep no project. */
function noMatchText(query: string, status: ProjectFilter): string {
  if (query) return `No project matches “${query}”.`;
  const label = PROJECT_FILTERS.find((f) => f.value === status)?.label ?? "";
  return `No ${label.toLowerCase()} projects.`;
}

/**
 * Every project, newest first; the status chips (?status=) and the top bar
 * search (?q=) narrow them. A queued or running card shows its step and
 * opens its processing view.
 */
export function ProjectsPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const status = statusOf(params.get("status"));

  function setStatus(next: ProjectFilter) {
    const updated = new URLSearchParams(params);
    if (next === "all") updated.delete("status");
    else updated.set("status", next);
    setParams(updated, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Projects"
        width="wide"
        description={
          query
            ? `Projects matching “${query}”.`
            : "Every video you processed, with its clips."
        }
        actions={
          <Button asChild>
            <Link to="/">
              <PlusIcon aria-hidden />
              New project
            </Link>
          </Button>
        }
      />
      <div className={cn(pageColumn("wide"), "pb-section")}>
        <div className="mb-6">
          <ChoiceChips
            label="Status"
            options={PROJECT_FILTERS}
            value={status}
            onChange={setStatus}
          />
        </div>
        <ProjectGrid
          pick={(projects) =>
            matchProjects(filterProjects(projects, status), query)
          }
          noMatch={noMatchText(query, status)}
        />
      </div>
    </>
  );
}
