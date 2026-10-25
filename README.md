# MCP Compatible Dify Tools

Dify extension plugin that exposes your Dify **tools** as an [MCP](https://modelcontextprotocol.io) server. Pick the tools you need on an endpoint — each one becomes an MCP tool with its input schema generated automatically. No workflow wrappers, no hand-written schemas.

Source code: https://github.com/neyara11/dify-plugin-mcp_compat_dify_tools

Russian version: [readme/README_ru_RU.md](readme/README_ru_RU.md)

## Why

Publishing a tool through Dify usually means building a workflow around it and publishing that as an app — even when the tool is self-contained and just has many input parameters. This plugin skips the middle layer: a Dify tool with a rich parameter list turns into an MCP tool with exactly that parameter list, and external MCP clients (Cherry Studio, Cursor, Roo Code, Kilo Code, Claude Desktop, Cline, LobeChat) can call it directly.

## Requirements

- Dify **1.2.0+**

## How parameters are exposed

| Dify tool parameter | In MCP input schema |
|---------------------|---------------------|
| `llm` form parameter | Exposed with its type, description and `enum` for select options |
| Settings parameter **without** a value in the endpoint config | Exposed — the client passes it per call |
| Settings parameter **with** a value in the endpoint config | Hidden and fixed — injected automatically on every call |
| File/files parameter | Skipped (MCP has no file type) — pass a file URL as a string |

Per-call arguments override values preset in the endpoint config. If several tools share the same name, the later one is renamed with a provider prefix so MCP tool names stay unique.

## Transports

| URL | Transport | Use |
|-----|-----------|-----|
| `.../mcp` | Streamable HTTP | Recommended, modern MCP clients |
| `.../sse` + `.../messages/` | HTTP with SSE (legacy) | Older clients only |

## Setup

### 1. Create an endpoint and add the tool list

![add_endpoint](./_assets/add_endpoint.png)

![add_tool_list](./_assets/add_tool_list.png)

![edit_tool](./_assets/edit_tool.png)

![save_endpoint](./_assets/save_endpoint.png)

> **Note:** changing the tool list of an existing endpoint takes effect only after the endpoint is disabled and re-enabled.

### 2. Copy the endpoint URL to your MCP client

![mcp_urls](./_assets/mcp_urls.png)

**Option 1 (recommended): Streamable HTTP**

![mcp_streamable_http_url](./_assets/mcp_streamable_http_url.png)

Example client config (Roo Code requires an explicit `type` for URL-based servers):

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "streamable-http",
      "url": "https://your-dify-host/e/your-endpoint-id/mcp"
    }
  }
}
```

**Option 2: legacy HTTP with SSE**

![mcp_sse_url](./_assets/mcp_sse_url.png)

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "sse",
      "url": "https://your-dify-host/e/your-endpoint-id/sse"
    }
  }
}
```

## Authentication

The optional **Auth token** endpoint setting protects all endpoint URLs. If set, every request must carry the token as one of:

- `Authorization: Bearer <token>` header (works in most clients via `headers`)
- `X-Api-Key: <token>` header
- `?token=<token>` query parameter (convenient for SSE clients that only take a URL)

```json
{
  "mcpServers": {
    "dify-tools": {
      "type": "streamable-http",
      "url": "https://your-dify-host/e/your-endpoint-id/mcp?token=your-token",
      "headers": { "Authorization": "Bearer your-token" }
    }
  }
}
```

## Changes in this fork (0.2.0)

Based on [junjiem/mcp_compat_dify_tools](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools) 0.1.1. Fixes:

- Removed debug output that was printed over the JSON response and broke `tools/call` in the plugin daemon ([#7](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/7), [#9](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/9)).
- Protocol version is now negotiated with the client (echoes `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`) instead of a hard-coded `2024-11-05`.
- `select` parameters are exposed as `string` with an `enum` — previously the schema contained the invalid JSON Schema type `select`, which made strict clients reject tools.
- Unset settings parameters can now be passed per call ([#12](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/12)).
- Optional `auth_token` endpoint setting (Bearer / `X-Api-Key` / `?token=`).
- Tool execution errors return `isError: true` with the error text so the calling LLM can see what happened; unknown tool names return JSON-RPC `-32602`.
- Added `ping`, proper `notifications/*` handling (202 with empty body).
- Fixed `GET /mcp` returning a malformed body (a dict was passed to the response as an iterable).
- MCP tool names are made unique when several tools share a name.
- Shared endpoint logic consolidated in `mcp_common.py`.

Not fixed upstream, out of scope here: endpoint URL display bugs in Dify core ([#1](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/1) extra `}`, [#14](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools/issues/14) `localhost` in generated URL) — these come from the Dify instance configuration, not the plugin.

## Origin

This is a fork of [junjiem/dify-plugin-mcp_compat_dify_tools](https://github.com/junjiem/dify-plugin-mcp_compat_dify_tools) (MIT-style open source, no license file in upstream), which was built as a reference to [hjlarry/dify-plugin-mcp_server](https://github.com/hjlarry/dify-plugin-mcp_server). All credit for the original design goes to the upstream authors; this fork adds the fixes listed above.

## Installing

**From a .difypkg file:** build with `dify plugin package .` and upload it on the Dify plugin management page.

**Via GitHub:** on the plugin management page choose install via GitHub, enter the repository address, select the version and package file.

![install_plugin_via_github](_assets/install_plugin_via_github.png)

### FAQ: "plugin verification has been enabled, and the plugin ... has a bad signature"

Add `FORCE_VERIFYING_SIGNATURE=false` to the end of your `.env` file and restart Dify. This allows installing plugins that are not listed (and thus not verified) in the Dify Marketplace — use at your own risk.

### FAQ: offline installation

For a true offline package (dependencies bundled, no internet needed), see [junjiem/dify-plugin-repackaging](https://github.com/junjiem/dify-plugin-repackaging).

### FAQ: client connects but the tool call fails

- Make sure the URL matches the transport: `.../mcp` with `type: "streamable-http"`, `.../sse` with `type: "sse"`.
- Roo Code requires an explicit `type` for URL-based servers; Kilo Code auto-detects the transport.
- If you set `auth_token`, pass it via header or `?token=` — otherwise requests are rejected with 401.
