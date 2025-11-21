# Lunr Search MCP Server

Model Context Protocol (MCP) server for static documentation sites using
[Lunr.js](https://lunrjs.com/) search indexes.

This MCP server provides tools to search and retrieve documentation from any
static site with Lunr.js search indexes, including sites built with
[Docusaurus](https://docusaurus.io).

**⚠️ Configuration Required**: This MCP server requires you to configure at least one
Lunr.js search index URL via the `LUNR_SITES` environment variable. It will not work
without this configuration.

## Features

- **Search Documentation**: Find relevant pages across the entire documentation site
- **Retrieve Pages**: Get full page content in markdown format with source URLs
- **Multi-site Support**: Configure multiple sites with Lunr.js indexes simultaneously
- **Dual-index Support**: Automatically handles sites with multiple search indexes
- **Dynamic Tool Generation**: Automatically creates MCP tools for each configured site

## Prerequisites

### Installation Requirements

- Install [uv](https://docs.astral.sh/uv/) from Astral or the [GitHub README](https://github.com/astral-sh/uv)
- Install Python 3.10 or newer using `uv python install 3.10` (or a more recent version)

### Quick Install

| Cursor | VS Code |
|:------:|:-------:|
| [![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en/install-mcp?name=lunr-mcp&config=eyJjb21tYW5kIjoidXZ4IGx1bnItbWNwQGxhdGVzdCIsImVudiI6eyJGQVNUTUNQX0xPR19MRVZFTCI6IkVSUk9SIiwiTFVOUl9TSVRFUyI6Im15c2l0ZT1odHRwczovL3lvdXItc2l0ZS5jb20vc2VhcmNoLWluZGV4Lmpzb24ifSwiZGlzYWJsZWQiOmZhbHNlLCJhdXRvQXBwcm92ZSI6WyJzZWFyY2hfbXlzaXRlIiwiZ2V0X215c2l0ZV9wYWdlIl19) | [![Install on VS Code](https://img.shields.io/badge/Install_on-VS_Code-FF9900?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=Lunr%20Search%20MCP%20Server&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22lunr-mcp%40latest%22%5D%2C%22env%22%3A%7B%22FASTMCP_LOG_LEVEL%22%3A%22ERROR%22%2C%22LUNR_SITES%22%3A%22mysite%3Dhttps%3A%2F%2Fyour-site.com%2Fsearch-index.json%22%7D%2C%22disabled%22%3Afalse%2C%22autoApprove%22%3A%5B%22search_mysite%22%2C%22get_mysite_page%22%5D%7D) |

## Installation

### Kiro CLI

Configure the MCP server in your MCP client (like [Kiro CLI](https://kiro.dev/docs/cli/)) configuration (`~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "lunr": {
      "command": "uvx",
      "args": ["lunr-mcp@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR",
        "LUNR_SITES": "mysite=https://your-site.com/search-index.json"
      },
      "disabled": false,
      "autoApprove": ["search_mysite", "get_mysite_page"]
    }
  }
}
```

### Multiple Sites

To configure multiple documentation sites:

```json
{
  "mcpServers": {
    "lunr": {
      "command": "uvx",
      "args": ["lunr-mcp@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR",
        "LUNR_SITES": "site1=https://site1.com/search-index.json,site2=https://site2.com/search-index.json"
      },
      "disabled": false,
      "autoApprove": ["search_site1", "get_site1_page", "search_site2", "get_site2_page"]
    }
  }
}
```

### Windows Installation

For Windows users, the MCP server configuration format is slightly different:

```json
{
  "mcpServers": {
    "lunr": {
      "disabled": false,
      "timeout": 60,
      "type": "stdio",
      "command": "uv",
      "args": [
        "tool",
        "run",
        "--from",
        "lunr-mcp@latest",
        "lunr-mcp.exe"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR",
        "LUNR_SITES": "mysite=https://your-site.com/search-index.json"
      }
    }
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FASTMCP_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | WARNING |
| `LUNR_SITES` | Comma-separated list of site configurations in format `key=search_index_url` | (none - required) |
| `LUNR_MCP_LOG` | Enable file logging to `/tmp/lunr_mcp_*.log` (1, true, yes) | disabled |

## Logging

The server provides two types of logging:

**Client Logging** (always enabled):
- Sends informational messages to the LLM via MCP protocol
- Includes operation status, warnings, and errors
- Helps the LLM understand what's happening

**File Logging** (optional):
- Disabled by default
- Enable with `LUNR_MCP_LOG=1` to log to `/tmp/lunr_mcp_YYYYMMDD_HHMMSS.log`
- Logs all requests, responses, URLs, HTTP status codes, and errors
- Useful for debugging issues

Example with file logging enabled:
```json
{
  "env": {
    "LUNR_MCP_LOG": "1",
    "LUNR_SITES": "mysite=https://your-site.com/search-index.json"
  }
}
```

## Performance

**Large Documentation Sites**: Sites with very large search indexes (>10,000 items) use async loading with a 1.5-second timeout:

- First search returns a "loading" message if index isn't ready
- The LLM can retry the search (index loads in background)
- Once loaded, the index is cached and searches are instant
- Typical large site (20k+ items) loads in 3-5 seconds

## Search Capabilities

This MCP server provides basic search functionality over Lunr.js indexes:

- **Phrase matching**: Exact phrase matches are prioritized (highest relevance)
- **Word matching**: Falls back to matching individual words when exact phrases don't match
- **Scoring**: Results are ranked by relevance (exact matches first, then by word count)

## Corporate Network Support

For corporate environments with proxy servers:

```json
{
  "env": {
    "HTTPS_PROXY": "http://proxy.company.com:8080",
    "HTTP_PROXY": "http://proxy.company.com:8080"
  }
}
```

For authenticated proxies:

```json
{
  "env": {
    "HTTPS_PROXY": "http://username:password@proxy.company.com:8080"
  }
}
```

## Basic Usage

Example queries (replace `mysite` with your configured site key):

- "Search mysite documentation for authentication"
- "How do I configure the API in mysite?"
- "What features are available in mysite?"

## Development

### From Source

```bash
git clone https://github.com/ojacques/lunr-mcp.git
cd lunr-mcp
pip install -e .
lunr-mcp
```

### Publishing

This package is automatically published to PyPI when a new release is created on GitHub:

1. Update version in `pyproject.toml`
2. Create a new release on GitHub with a tag (e.g., `v0.1.0`)
3. GitHub Actions will automatically build and publish to PyPI

Note: Requires PyPI trusted publishing to be configured for the repository.

## License

MIT
