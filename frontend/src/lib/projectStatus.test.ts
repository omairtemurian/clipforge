import { describe, expect, it } from "vitest";
import { job, project } from "@/testing/mockApi";
import {
  activeCount,
  filterProjects,
  isArchived,
  isActive,
  isNew,
  matchProjects,
  projectProgress,
} from "./projectStatus";

describe("isActive and activeCount", () => {
  it("counts queued and running projects only", () => {
    const projects = (["queued", "running", "done", "failed"] as const).map(
      (status, id) => project({ id, status }),
    );

    expect(projects.map(isActive)).toEqual([true, true, false, false]);
    expect(activeCount(projects)).toBe(2);
    expect(activeCount([])).toBe(0);
  });
});

describe("projectProgress", () => {
  it("is null for a project that is done or failed", () => {
    const running = job({ status: "running", step: "curate" });

    expect(projectProgress(project({ status: "done" }), running)).toBeNull();
    expect(projectProgress(project({ status: "failed" }), running)).toBeNull();
  });

  it("waits in the queue at 0 % without a job or while it is queued", () => {
    const waiting = {
      label: "Waiting in the queue",
      percent: 0,
      etaSeconds: null,
    };
    const queued = project({ status: "queued" });

    expect(projectProgress(queued, undefined)).toEqual(waiting);
    expect(projectProgress(queued, job())).toEqual(waiting);
  });

  it("names the step and takes the percent and ETA the server weighed", () => {
    const running = project({ status: "running" });

    expect(
      projectProgress(
        running,
        job({
          status: "running",
          step: "transcribe",
          progress: 0.5,
          overall_progress: 0.48,
          eta_seconds: 300,
        }),
      ),
    ).toEqual({ label: "Transcribe", percent: 48, etaSeconds: 300 });
    expect(
      projectProgress(
        running,
        job({ status: "running", step: "enrich", overall_progress: 0.381 }),
      ),
    ).toEqual({ label: "Analyze audio", percent: 38, etaSeconds: null });
  });

  it("uses the project's own progress before its job is known", () => {
    const running = project({
      status: "running",
      overall_progress: 0.3,
      eta_seconds: 90,
    });

    expect(projectProgress(running, undefined)).toEqual({
      label: "Starting",
      percent: 30,
      etaSeconds: 90,
    });
  });

  it("is starting when the running job names no step", () => {
    expect(
      projectProgress(
        project({ status: "running" }),
        job({ status: "running", step: "" }),
      ),
    ).toEqual({ label: "Starting", percent: 0, etaSeconds: null });
  });

  it("follows the job when the project row lags behind", () => {
    expect(
      projectProgress(
        project({ status: "running" }),
        job({ status: "done", step: "render", progress: 1 }),
      ),
    ).toEqual({ label: "Captions", percent: 100, etaSeconds: null });
  });
});

describe("isNew", () => {
  it("is a done project that was not opened yet", () => {
    expect(isNew(project({ status: "done", opened_at: null }))).toBe(true);
    expect(isNew(project({ status: "done", opened_at: "2026-11-02" }))).toBe(
      false,
    );
    expect(isNew(project({ status: "running", opened_at: null }))).toBe(false);
  });
});

describe("matchProjects", () => {
  const projects = [
    project({ id: 1, title: "Late Night Set" }),
    project({ id: 2, title: "", source_url: "https://youtu.be/talk" }),
  ];

  it("keeps the projects whose name contains the query, in any case", () => {
    expect(matchProjects(projects, " night ").map(({ id }) => id)).toEqual([1]);
    expect(matchProjects(projects, "TALK").map(({ id }) => id)).toEqual([2]);
    expect(matchProjects(projects, "")).toBe(projects);
  });
});

describe("filterProjects", () => {
  const projects = [
    project({ id: 1, status: "queued" }),
    project({ id: 2, status: "running" }),
    project({ id: 3, status: "done" }),
    project({ id: 4, status: "failed" }),
    project({ id: 5, status: "done", archived_at: "2026-11-01T10:00:00" }),
  ];
  const ids = (filter: Parameters<typeof filterProjects>[1]) =>
    filterProjects(projects, filter).map(({ id }) => id);

  it("keeps the projects of a status, archived ones apart", () => {
    expect(ids("all")).toEqual([1, 2, 3, 4, 5]);
    expect(ids("processing")).toEqual([1, 2]);
    expect(ids("ready")).toEqual([3]);
    expect(ids("failed")).toEqual([4]);
    expect(ids("archived")).toEqual([5]);
  });

  it("tells an archived project", () => {
    expect(isArchived(projects[4])).toBe(true);
    expect(isArchived(projects[2])).toBe(false);
  });
});
