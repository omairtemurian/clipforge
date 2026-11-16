import { vi } from "vitest";

/** A stand-in for the browser's EventSource that a test feeds by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  onmessage: ((message: MessageEvent<string>) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  /** Deliver one server-sent event whose data is the JSON of payload. */
  emit(payload: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(payload) }),
    );
  }
}

/** Replace EventSource with FakeEventSource and forget earlier instances. */
export function mockEventSource() {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
}
