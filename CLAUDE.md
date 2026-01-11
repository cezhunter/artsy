# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Python client for the Art Institute of Chicago public API, enabling artwork search and IIIF image downloads. Includes the API's OpenAPI 3.1 specification.

## Quick Start

```bash
# Install dependency
pip install requests

# Run example
python example.py
```

## Usage

```python
from artic_client import ArticClient, search, download

# Search for artworks
artworks = search("impressionism", limit=10)

# Download full-resolution image
download(artworks[0], "output.jpg", size="max")

# Or use the client directly for more control
client = ArticClient()
result = client.search_artworks("monet", size=20, offset=0)
client.download_image(result.artworks[0], "downloads/", size="!800,800")
```

## Architecture

- `artic_client.py` - Main client module
  - `Artwork` dataclass with IIIF URL generation
  - `SearchResult` for paginated results
  - `ArticClient` for API interactions and image downloads
  - Convenience functions: `search()`, `download()`

## API Details

**Base URL:** `https://api.artic.edu/api/v1/`

**IIIF Image URL Pattern:** `https://www.artic.edu/iiif/2/{image_id}/full/{size}/0/default.jpg`

**IIIF Size Options:**
- `max` - Full resolution
- `!800,800` - Fit within box
- `400,` - Fixed width
- `,300` - Fixed height
- `pct:50` - Percentage scale

**Search Parameters:**
- `q` - Text search query
- `size` - Results per page (max 100)
- `from` - Pagination offset
- `fields` - Comma-separated field list
