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
from markdownify import markdownify as md
from fastmcp import FastMCP

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
        async def search_tool(query: str, limit: int = 10) -> list[dict] | dict:
            # Check if already cached
            if idx_url in _cache:
                index_data = _cache[idx_url]
                return search_items(index_data, query, limit, b_url)
            
            # Check if loading is in progress
            if idx_url in _loading:
                task = _loading[idx_url]
            else:
                task = asyncio.create_task(fetch_search_index(idx_url))
                _loading[idx_url] = task
            
            # Wait up to 1.5 seconds
            try:
                index_data = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
                if idx_url in _loading:
                    del _loading[idx_url]
                return search_items(index_data, query, limit, b_url)
            except asyncio.TimeoutError:
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
        async def get_page_tool(location: str) -> dict:
            if idx_url in _cache:
                index_data = _cache[idx_url]
            else:
                if idx_url in _loading:
                    task = _loading[idx_url]
                else:
                    task = asyncio.create_task(fetch_search_index(idx_url))
                    _loading[idx_url] = task
                
                try:
                    index_data = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
                    if idx_url in _loading:
                        del _loading[idx_url]
                except asyncio.TimeoutError:
                    return {
                        "error": "loading",
                        "title": "Index Loading - Please Retry",
                        "message": f"Search index for {key} is still loading. Please retry in a moment.",
                    }
            
            base_location = location.split("#")[0]
            
            # Handle both single index dict and array of indexes
            indexes = index_data if isinstance(index_data, list) else [index_data]
            
            # Find matching document
            doc = None
            for index in indexes:
                for d in index.get("documents", []):
                    if d.get("u", "").split("#")[0] == base_location:
                        doc = d
                        break
                if doc:
                    break
            
            if not doc:
                return {"error": f"Page not found: {location}"}
            
            page_url = f"{b_url}{base_location}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(page_url)
                    markdown_text = md(response.text, heading_style="ATX") if response.status_code == 200 else f"# {doc.get('t')}\n\nContent not available (HTTP {response.status_code})"
            except Exception as e:
                markdown_text = f"# {doc.get('t')}\n\nError fetching content: {str(e)}"
            
            return {
                "title": doc.get("t"),
                "url": page_url,
                "path": doc.get("b", []),
                "content": markdown_text,
            }
        get_page_tool.__doc__ = f"""Get the full content of a specific documentation page for {key}.
        
        Args:
            location: Page URL path from search results (e.g., "/docs/get-started/")
        
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
    mcp.run()


if __name__ == "__main__":
    main()
