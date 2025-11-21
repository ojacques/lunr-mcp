"""Lunr Search MCP Server - Search and retrieve documentation from static sites with Lunr.js indexes.

Supports any static documentation site using Lunr.js (https://lunrjs.com/), including
Docusaurus (https://docusaurus.io).

Copyright (c) 2025 Olivier JACQUES <ojacques2@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
from typing import Any
import asyncio
import httpx
import tempfile
from datetime import datetime
from markdownify import markdownify as md
from fastmcp import FastMCP, Context
from bs4 import BeautifulSoup

# Setup logging to temporary file (controlled by LUNR_MCP_LOG environment variable)
ENABLE_FILE_LOGGING = os.getenv("LUNR_MCP_LOG", "").lower() in ("1", "true", "yes")
LOG_FILE = os.path.join(tempfile.gettempdir(), f"lunr_mcp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log") if ENABLE_FILE_LOGGING else None

def log_to_file(message: str):
    """Write log message to temporary file if logging is enabled."""
    if ENABLE_FILE_LOGGING and LOG_FILE:
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")

if ENABLE_FILE_LOGGING:
    log_to_file(f"Lunr MCP Server starting - Log file: {LOG_FILE}")
    print(f"Lunr MCP Server - Logging to: {LOG_FILE}", flush=True)

# Parse sites from environment variable
# Format: "key1=index_url1,key2=index_url2"
SITES = {}
sites_config = os.getenv("LUNR_SITES", "")
if sites_config:
    for site_def in sites_config.split(","):
        key, index_url = site_def.strip().split("=")
        SITES[key.strip()] = index_url.strip()

# Cache for search indexes
_cache: dict[str, Any] = {}
_loading: dict[str, asyncio.Task] = {}

mcp = FastMCP("Lunr Search Documentation")

if not SITES:
    # Register a placeholder tool that explains configuration is needed
    @mcp.tool()
    def configuration_required() -> dict:
        """Configuration required - no search indexes configured.

        Returns:
            Instructions for configuring the LUNR_SITES environment variable.
        """
        return {
            "error": "No search indexes configured",
            "message": "Please set the LUNR_SITES environment variable with your Lunr.js search index URL(s).",
            "example": "LUNR_SITES=mysite=https://your-site.com/search-index.json",
            "format": "key1=index_url1,key2=index_url2 for multiple sites"
        }


async def fetch_search_index(index_url: str) -> dict:
    """Fetch Lunr.js search index from URL."""
    if index_url in _cache:
        return _cache[index_url]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(index_url)
        response.raise_for_status()
        data = response.json()
        _cache[index_url] = data
        return data


def clean_html(html: str) -> str:
    """Extract content starting from h1 tag."""
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')

    if not h1:
        return md(html, heading_style="ATX")

    content = []
    for elem in h1.find_all_next():
        content.append(str(elem))

    markdown = md(''.join([str(h1)] + content), heading_style="ATX")
    return markdown


def search_items(index_data: dict | list, query: str, limit: int = 10, base_url: str = "") -> list[dict]:
    """Search through documents in Lunr.js indexes."""
    query_lower = query.lower()
    query_words = query_lower.split()
    results = []
    seen_urls = set()

    # Handle both single index dict and array of indexes
    indexes = index_data if isinstance(index_data, list) else [index_data]

    for index in indexes:
        for doc in index.get("documents", []):
            title = doc.get("t", "").lower()
            url = doc.get("u", "")
            breadcrumb = doc.get("b", [])
            path = " ".join(breadcrumb).lower()

            if query_lower in title or query_lower in path:
                score = 100
            elif any(word in title or word in path for word in query_words):
                score = sum(1 for word in query_words if word in title or word in path) * 10
            else:
                continue

            base_url_path = url.split("#")[0]
            if base_url_path not in seen_urls:
                seen_urls.add(base_url_path)
                results.append({
                    "title": doc.get("t"),
                    "url": f"{base_url}{base_url_path}",
                    "path": breadcrumb,
                    "_score": score
                })

    results.sort(key=lambda x: (-x["_score"], x["title"]))
    return [{"title": r["title"], "url": r["url"], "path": r["path"]} for r in results[:limit]]


# Dynamically create tools for each configured site
for site_key, index_url in SITES.items():
    # Derive base URL from index URL (remove /search-index.json or similar)
    base_url = index_url.rsplit("/", 1)[0] if "/" in index_url else index_url

    def make_search_tool(idx_url: str, b_url: str, key: str):
        async def search_tool(query: str, limit: int = 10, ctx: Context = None) -> list[dict] | dict:
            log_to_file(f"Search request - site: {key}, query: '{query}', limit: {limit}")
            if ctx:
                await ctx.info(f"Searching {key} for: '{query}'")

            # Check if already cached
            if idx_url in _cache:
                log_to_file(f"Using cached index for {key}")
                if ctx:
                    await ctx.debug(f"Using cached search index for {key}")
                index_data = _cache[idx_url]
                results = search_items(index_data, query, limit, b_url)
                log_to_file(f"Search completed - found {len(results)} results")
                if ctx:
                    await ctx.info(f"Found {len(results)} results")
                return results

            # Check if loading is in progress
            if idx_url in _loading:
                task = _loading[idx_url]
                log_to_file(f"Index loading in progress for {key}")
            else:
                log_to_file(f"Starting to load index for {key} from {idx_url}")
                if ctx:
                    await ctx.info(f"Loading search index for {key}...")
                task = asyncio.create_task(fetch_search_index(idx_url))
                _loading[idx_url] = task

            # Wait up to 1.5 seconds
            try:
                index_data = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
                if idx_url in _loading:
                    del _loading[idx_url]
                log_to_file(f"Index loaded successfully for {key}")
                if ctx:
                    await ctx.info(f"Search index loaded for {key}")
                results = search_items(index_data, query, limit, b_url)
                log_to_file(f"Search completed - found {len(results)} results")
                if ctx:
                    await ctx.info(f"Found {len(results)} results")
                return results
            except asyncio.TimeoutError:
                log_to_file(f"Index loading timeout for {key} - still loading in background")
                if ctx:
                    await ctx.warning(f"Search index for {key} is still loading. Please retry in a moment.")
                return [{
                    "error": "loading",
                    "title": "Index Loading - Please Retry",
                    "message": f"Search index for {key} is still loading (large index ~20k items). This is normal for the first search. Please retry your search in a moment - subsequent searches will be instant.",
                    "url": "",
                    "path": []
                }]
        search_tool.__doc__ = f"""Search {key} documentation.

        Args:
            query: Search query string
            limit: Maximum number of results to return (default: 10)

        Returns:
            List of matching documentation pages with title, url, and path (breadcrumb).
            Always include the url in your response to users.
        """
        return search_tool

    def make_get_page_tool(idx_url: str, b_url: str, key: str):
        async def get_page_tool(location: str, ctx: Context = None) -> dict:
            log_to_file(f"Get page request - site: {key}, location: {location}")
            if ctx:
                await ctx.info(f"Fetching page from {key}: {location}")

            if idx_url in _cache:
                index_data = _cache[idx_url]
                log_to_file(f"Using cached index for {key}")
            else:
                if idx_url in _loading:
                    task = _loading[idx_url]
                    log_to_file(f"Index loading in progress for {key}")
                else:
                    log_to_file(f"Starting to load index for {key}")
                    if ctx:
                        await ctx.info(f"Loading search index for {key}...")
                    task = asyncio.create_task(fetch_search_index(idx_url))
                    _loading[idx_url] = task

                try:
                    index_data = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
                    if idx_url in _loading:
                        del _loading[idx_url]
                    log_to_file(f"Index loaded successfully for {key}")
                except asyncio.TimeoutError:
                    log_to_file(f"Index loading timeout for {key}")
                    if ctx:
                        await ctx.warning(f"Search index for {key} is still loading. Please retry in a moment.")
                    return {
                        "error": "loading",
                        "title": "Index Loading - Please Retry",
                        "message": f"Search index for {key} is still loading. Please retry in a moment.",
                    }

            base_location = location.split("#")[0]

            # Extract path from URL if full URL was provided
            if base_location.startswith("http://") or base_location.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(base_location)
                base_location = parsed.path
                log_to_file(f"Extracted path from URL: {base_location}")
                if ctx:
                    await ctx.debug(f"Extracted path: {base_location}")

            # Handle both single index dict and array of indexes
            indexes = index_data if isinstance(index_data, list) else [index_data]

            # Find matching document
            doc = None
            for index in indexes:
                for d in index.get("documents", []):
                    doc_path = d.get("u", "").split("#")[0]
                    if doc_path == base_location:
                        doc = d
                        log_to_file(f"Found matching document: {doc_path}")
                        break
                if doc:
                    break

            if not doc:
                log_to_file(f"Page not found - site: {key}, location: {location}, extracted path: {base_location}")
                if ctx:
                    await ctx.error(f"Page not found: {location}")
                return {"error": f"Page not found: {location}"}

            page_url = f"{b_url}{base_location}"
            log_to_file(f"Fetching page content from: {page_url}")
            if ctx:
                await ctx.debug(f"Fetching content from URL: {page_url}")

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(page_url)
                    if response.status_code == 200:
                        log_to_file(f"Page fetched successfully - status: {response.status_code}")
                        if ctx:
                            await ctx.info(f"Page content retrieved successfully")
                        markdown_text = clean_html(response.text)
                    else:
                        log_to_file(f"Page fetch failed - status: {response.status_code}, url: {page_url}")
                        if ctx:
                            await ctx.warning(f"Page returned HTTP {response.status_code}")
                        markdown_text = f"# {doc.get('t')}\n\nContent not available (HTTP {response.status_code})"
            except Exception as e:
                log_to_file(f"Error fetching page - url: {page_url}, error: {str(e)}")
                if ctx:
                    await ctx.error(f"Failed to fetch page: {str(e)}")
                markdown_text = f"# {doc.get('t')}\n\nError fetching content: {str(e)}"

            return {
                "title": doc.get("t"),
                "url": page_url,
                "path": doc.get("b", []),
                "content": markdown_text,
            }
        get_page_tool.__doc__ = f"""Get the full content of a specific documentation page for {key}.

        Args:
            location: Page URL or path from search results.
                     Can be a full URL (e.g., "https://example.com/docs/page/")
                     or just the path (e.g., "/docs/page/")

        Returns:
            Dictionary with title, url, path (breadcrumb), and markdown content.
            Always include the url in your response to users.
        """
        return get_page_tool

    # Register tools with descriptive names
    mcp.tool(
        name=f"search_{site_key}",
        description=f"Search {site_key} documentation"
    )(make_search_tool(index_url, base_url, site_key))

    mcp.tool(
        name=f"get_{site_key}_page",
        description=f"Get page from {site_key} documentation"
    )(make_get_page_tool(index_url, base_url, site_key))


def main():
    """Run the MCP server."""
    log_to_file(f"Starting MCP server with {len(SITES)} configured site(s)")
    for site_key in SITES:
        log_to_file(f"  - {site_key}: {SITES[site_key]}")
    mcp.run()


if __name__ == "__main__":
    main()
