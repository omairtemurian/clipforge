import { describe, expect, it } from "vitest";
import type { AgentSetup } from "@/api/types";
import {
  KEY_PLACEHOLDER,
  mcpClients,
  serverEnv,
  shellQuote,
} from "./mcpSnippets";

const SETUP: AgentSetup = {
  api_url: "http://127.0.0.1:8000",
  project_dir: "/Users/me/clipforge",
  mcp_command: "uv",
  mcp_args: ["run", "--project", "/Users/me/clipforge", "clipforge-mcp"],
  docs_url: "http://127.0.0.1:8000/api/docs",
};
const KEY = "cfk_abc-123";

function snippet(clientId: string, index = 0, setup = SETUP) {
  const client = mcpClients(setup, KEY).find(({ id }) => id === clientId);
  return client!.snippets[index]!.code;
}

describe("MCP snippets", () => {
  it("quotes only what the shell would split", () => {
    expect(shellQuote("/Users/me/clipforge")).toBe("/Users/me/clipforge");
    expect(shellQuote("/Users/me/My Clips")).toBe("'/Users/me/My Clips'");
    expect(shellQuote("it's")).toBe(`'it'\\''s'`);
  });

  it("sets the URL only when the app is not at the default address", () => {
    expect(serverEnv(SETUP, KEY)).toEqual({ CLIPFORGE_API_KEY: KEY });
    expect(
      serverEnv({ ...SETUP, api_url: "http://localhost:9000" }, KEY),
    ).toEqual({
      CLIPFORGE_API_KEY: KEY,
      CLIPFORGE_URL: "http://localhost:9000",
    });
  });

  it("adds the server with the Hermes CLI, --args last", () => {
    expect(snippet("hermes")).toBe(
      [
        "hermes mcp add clipforge \\",
        "  --command uv \\",
        "  --env CLIPFORGE_API_KEY=cfk_abc-123 \\",
        "  --args run --project /Users/me/clipforge clipforge-mcp",
        "hermes mcp test clipforge",
      ].join("\n"),
    );
  });

  it("writes the Hermes config.yaml entry", () => {
    expect(snippet("hermes", 1)).toBe(
      [
        "mcp_servers:",
        "  clipforge:",
        '    command: "uv"',
        "    args:",
        '      - "run"',
        '      - "--project"',
        '      - "/Users/me/clipforge"',
        '      - "clipforge-mcp"',
        "    env:",
        '      CLIPFORGE_API_KEY: "cfk_abc-123"',
        "    enabled: true",
      ].join("\n"),
    );
  });

  it("writes mcpServers JSON for Claude Desktop and other clients", () => {
    const expected = {
      mcpServers: {
        clipforge: {
          command: "uv",
          args: SETUP.mcp_args,
          env: { CLIPFORGE_API_KEY: KEY },
        },
      },
    };
    expect(JSON.parse(snippet("claude-desktop"))).toEqual(expected);
    expect(JSON.parse(snippet("generic"))).toEqual(expected);
  });

  it("adds the server with the Claude Code and Copilot CLIs", () => {
    const at = { ...SETUP, api_url: "http://localhost:9000" };
    expect(snippet("claude-code", 0, at)).toBe(
      [
        "claude mcp add clipforge --scope user \\",
        "  -e CLIPFORGE_API_KEY=cfk_abc-123 \\",
        "  -e CLIPFORGE_URL=http://localhost:9000 \\",
        "  -- uv run --project /Users/me/clipforge clipforge-mcp",
      ].join("\n"),
    );
    expect(snippet("copilot")).toBe(
      [
        "copilot mcp add clipforge \\",
        "  --env CLIPFORGE_API_KEY=cfk_abc-123 \\",
        "  -- uv run --project /Users/me/clipforge clipforge-mcp",
      ].join("\n"),
    );
  });

  it("writes a VS Code stdio server", () => {
    expect(JSON.parse(snippet("copilot", 1))).toEqual({
      servers: {
        clipforge: {
          type: "stdio",
          command: "uv",
          args: SETUP.mcp_args,
          env: { CLIPFORGE_API_KEY: KEY },
        },
      },
    });
  });

  it("uses the placeholder when no key is given", () => {
    const code = mcpClients(SETUP, KEY_PLACEHOLDER)[0]!.snippets[0]!.code;
    expect(code).toContain(`CLIPFORGE_API_KEY=${KEY_PLACEHOLDER}`);
  });
});
