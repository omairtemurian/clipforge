import { describe, expect, it } from "vitest";
import {
  INGEST_CONVERT_BAND,
  PROCESSING_STEPS,
  formatElapsed,
  logText,
  overallProgress,
  stepIndex,
  stepStates,
  subStep,
  type JobEvent,
} from "./processingSteps";

function event(overrides: Partial<JobEvent>): JobEvent {
  return {
    step: "",
    progress: 0,
    status: "running",
    message: "",
    ...overrides,
  };
}

describe("stepStates", () => {
  it("has the seven steps of SPEC 8.3", () => {
    expect(PROCESSING_STEPS.map((step) => step.label)).toEqual([
      "Download",
      "Transcribe",
      "Analyze audio",
      "Find clips",
      "Score",
      "Reframe",
      "Captions",
    ]);
  });

  it("has every step pending before the first event and while queued", () => {
    const pending = Array(7).fill("pending");
    expect(stepStates(null)).toEqual(pending);
    expect(stepStates(event({ status: "queued" }))).toEqual(pending);
  });

  it("marks the steps before the current one done", () => {
    expect(stepStates(event({ step: "curate", progress: 0.4 }))).toEqual([
      "done",
      "done",
      "done",
      "running",
      "pending",
      "pending",
      "pending",
    ]);
  });

  it("maps several job steps onto one line", () => {
    expect(stepIndex("signals")).toBe(2);
    expect(stepIndex("visuals")).toBe(2);
    expect(stepIndex("enrich")).toBe(2);
    expect(stepIndex("snap")).toBe(4);
    expect(stepIndex("render")).toBe(6);
    expect(stepIndex("nonsense")).toBe(-1);
  });

  it("starts at the first step while a running job has no step yet", () => {
    expect(stepStates(event({}))[0]).toBe("running");
  });

  it("marks the current step failed when the job failed", () => {
    expect(stepStates(event({ step: "transcribe", status: "failed" }))).toEqual(
      ["done", "failed", "pending", "pending", "pending", "pending", "pending"],
    );
  });

  it("has every step done when the job is done", () => {
    expect(stepStates(event({ step: "render", status: "done" }))).toEqual(
      Array(7).fill("done"),
    );
  });
});

describe("overallProgress", () => {
  it("is 0 before the job runs and 1 when it is done", () => {
    expect(overallProgress(null)).toBe(0);
    expect(overallProgress(event({ status: "queued" }))).toBe(0);
    expect(overallProgress(event({ status: "done", step: "render" }))).toBe(1);
  });

  it("adds the progress inside the current step", () => {
    const half = overallProgress(event({ step: "ingest", progress: 0.5 }));
    expect(half).toBeCloseTo(0.5 / 7);
    const third = overallProgress(event({ step: "transcribe", progress: 0 }));
    expect(third).toBeCloseTo(1 / 7);
  });

  it("splits the weight of a line with several job steps", () => {
    const enrich = overallProgress(event({ step: "enrich", progress: 0.5 }));
    expect(enrich).toBeCloseTo((2 + 2.5 / 3) / 7);
  });

  it("keeps a progress outside 0..1 in range", () => {
    expect(overallProgress(event({ step: "ingest", progress: 5 }))).toBeCloseTo(
      1 / 7,
    );
  });
});

describe("logText and formatElapsed", () => {
  it("words the log lines for the user", () => {
    expect(logText(event({ step: "transcribe" }))).toBe("Started: Transcribe.");
    expect(logText(event({ status: "queued" }))).toBe("Waiting in the queue.");
    expect(logText(event({ status: "done" }))).toBe("All steps finished.");
    expect(logText(event({ status: "failed", message: "No audio." }))).toBe(
      "No audio.",
    );
  });

  it("formats the elapsed time", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(75.9)).toBe("1:15");
    expect(formatElapsed(3725)).toBe("1:02:05");
  });
});

describe("subStep", () => {
  it("is Converting video inside the ingest conversion band", () => {
    const start = subStep(event({ step: "ingest", progress: 0.51 }));
    expect(start).toEqual({ label: "Converting video", progress: 0 });
    const middle = subStep(event({ step: "ingest", progress: 0.705 }));
    expect(middle?.label).toBe("Converting video");
    expect(middle?.progress).toBeCloseTo(0.5);
    expect(subStep(event({ step: "ingest", progress: 0.89 }))?.progress).toBe(
      (0.89 - INGEST_CONVERT_BAND.start) /
        (INGEST_CONVERT_BAND.end - INGEST_CONVERT_BAND.start),
    );
  });

  it("is null while downloading, after the conversion and elsewhere", () => {
    expect(subStep(null)).toBeNull();
    expect(subStep(event({ step: "ingest", progress: 0.5 }))).toBeNull();
    expect(subStep(event({ step: "ingest", progress: 0.9 }))).toBeNull();
    expect(subStep(event({ step: "transcribe", progress: 0.6 }))).toBeNull();
    expect(
      subStep(event({ step: "ingest", progress: 0.6, status: "failed" })),
    ).toBeNull();
  });
});
