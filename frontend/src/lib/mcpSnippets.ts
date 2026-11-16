import type { AgentSetup } from "@/api/types";

/** The name the snippets give the ClipForge MCP server in each client. */
export const SERVER_NAME = "clipforge";
/** Stands in for the key in the snippets until one is made on the page. */
export const KEY_PLACEHOLDER = "cfk_YOUR_KEY";
// The variables and default address of backend/clipforge/mcp_server.py.
const KEY_ENV = "CLIPFORGE_API_KEY";
const URL_ENV = "CLIPFORGE_URL";
const DEFAULT_URL = "http://127.0.0.1:8000";

export type SnippetLanguage = "shell" | "json" | "yaml";

export interface Snippet {
  title: string;
  /** Where it goes or how to run it. */
  where: string;
  language: SnippetLanguage;
  code: string;
}

export interface McpClient {
  id: string;
  label: string;
  snippets: Snippet[];
}

/** An argument as the shell reads it: as is when it is plain, else in
 * single quotes. */
export function shellQuote(arg: string): string {
  return /^[\w@%+=:,./-]+$/.test(arg)
    ? arg
    : `'${arg.replaceAll("'", `'\\''`)}'`;
}

function shellLine(args: string[]): string {
  return args.map(shellQuote).join(" ");
}

/** One command over several lines, a group of arguments per line. */
function shellLines(groups: string[][]): string {
  return groups.map(shellLine).join(" \\\n  ");
}

/** The environment of the MCP server: the key, and the app's address when
 * it is not the server's default. */
export function serverEnv(
  setup: AgentSetup,
  key: string,
): Record<string, string> {
  const env: Record<string, string> = { [KEY_ENV]: key };
  if (setup.api_url !== DEFAULT_URL) env[URL_ENV] = setup.api_url;
  return env;
}

function envPairs(env: Record<string, string>): string[] {
  return Object.entries(env).map(([name, value]) => `${name}=${value}`);
}

function launch(setup: AgentSetup): string[] {
  return [setup.mcp_command, ...setup.mcp_args];
}

function stdioServer(setup: AgentSetup, key: string) {
  return {
    command: setup.mcp_command,
    args: setup.mcp_args,
    env: serverEnv(setup, key),
  };
}

function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/** `hermes mcp add` (its --args must come last), then a connection test. */
function hermesCli(setup: AgentSetup, key: string): string {
  const add = shellLines([
    ["hermes", "mcp", "add", SERVER_NAME],
    ["--command", setup.mcp_command],
    ["--env", ...envPairs(serverEnv(setup, key))],
    ["--args", ...setup.mcp_args],
  ]);
  return `${add}\nhermes mcp test ${SERVER_NAME}`;
}

/** The mcp_servers entry of ~/.hermes/config.yaml (strings JSON-quoted,
 * which YAML reads as double-quoted scalars). */
function hermesYaml(setup: AgentSetup, key: string): string {
  const quote = (text: string) => JSON.stringify(text);
  const env = Object.entries(serverEnv(setup, key)).map(
    ([name, value]) => `      ${name}: ${quote(value)}`,
  );
  return [
    "mcp_servers:",
    `  ${SERVER_NAME}:`,
    `    command: ${quote(setup.mcp_command)}`,
    "    args:",
    ...setup.mcp_args.map((arg) => `      - ${quote(arg)}`),
    "    env:",
    ...env,
    "    enabled: true",
  ].join("\n");
}

function mcpServersJson(setup: AgentSetup, key: string): string {
  return json({ mcpServers: { [SERVER_NAME]: stdioServer(setup, key) } });
}

/** `claude mcp add` / `copilot mcp add`: env flags, then the command after --. */
function addCommand(
  cli: string[],
  envFlag: string,
  setup: AgentSetup,
  key: string,
): string {
  const env = envPairs(serverEnv(setup, key)).map((pair) => [envFlag, pair]);
  return shellLines([cli, ...env, ["--", ...launch(setup)]]);
}

/** Ready-to-copy MCP configs for each supported agent, with key filled in
 * (or KEY_PLACEHOLDER). */
export function mcpClients(setup: AgentSetup, key: string): McpClient[] {
  return [
    {
      id: "hermes",
      label: "Hermes",
      snippets: [
        {
          title: "Add with the Hermes CLI",
          where: "Run in a terminal, then restart Hermes or /reload-mcp.",
          language: "shell",
          code: hermesCli(setup, key),
        },
        {
          title: "Or edit the config",
          where: "Add to ~/.hermes/config.yaml.",
          language: "yaml",
          code: hermesYaml(setup, key),
        },
      ],
    },
    {
      id: "claude-desktop",
      label: "Claude Desktop",
      snippets: [
        {
          title: "claude_desktop_config.json",
          where:
            "Settings → Developer → Edit Config, merge this in and restart Claude Desktop.",
          language: "json",
          code: mcpServersJson(setup, key),
        },
      ],
    },
    {
      id: "claude-code",
      label: "Claude Code",
      snippets: [
        {
          title: "Add with the Claude Code CLI",
          where: "Run in a terminal (user scope: every project can use it).",
          language: "shell",
          code: addCommand(
            ["claude", "mcp", "add", SERVER_NAME, "--scope", "user"],
            "-e",
            setup,
            key,
          ),
        },
      ],
    },
    {
      id: "copilot",
      label: "GitHub Copilot",
      snippets: [
        {
          title: "Copilot CLI",
          where: "Run in a terminal; saved in ~/.copilot/mcp-config.json.",
          language: "shell",
          code: addCommand(
            ["copilot", "mcp", "add", SERVER_NAME],
            "--env",
            setup,
            key,
          ),
        },
        {
          title: "VS Code",
          where:
            "Add to the mcp.json of your VS Code user profile (not the workspace: it holds the key).",
          language: "json",
          code: json({
            servers: {
              [SERVER_NAME]: { type: "stdio", ...stdioServer(setup, key) },
            },
          }),
        },
      ],
    },
    {
      id: "generic",
      label: "Other MCP clients",
      snippets: [
        {
          title: "mcpServers JSON",
          where: "For any client that reads an mcpServers config.",
          language: "json",
          code: mcpServersJson(setup, key),
        },
      ],
    },
  ];
}
