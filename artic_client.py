"""
Art Institute of Chicago API Client

A Python client for searching artworks and downloading images via IIIF.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


BASE_URL = "https://api.artic.edu/api/v1/"
IIIF_BASE_URL = "https://www.artic.edu/iiif/2/"


@dataclass
class Artwork:
    """Represents an artwork from the Art Institute of Chicago."""

    id: int
    title: str
    artist_display: str | None = None
    date_display: str | None = None
    medium_display: str | None = None
    dimensions: str | None = None
    image_id: str | None = None
    thumbnail: dict | None = None
    is_public_domain: bool = False
    credit_line: str | None = None
    department_title: str | None = None
    artwork_type_title: str | None = None
    style_title: str | None = None
    classification_title: str | None = None
    place_of_origin: str | None = None
    description: str | None = None
    alt_image_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "Artwork":
        """Create an Artwork from API response data."""
        return cls(
            id=data.get("id", 0),
            title=data.get("title", "Untitled"),
            artist_display=data.get("artist_display"),
            date_display=data.get("date_display"),
            medium_display=data.get("medium_display"),
            dimensions=data.get("dimensions"),
            image_id=data.get("image_id"),
            thumbnail=data.get("thumbnail"),
            is_public_domain=data.get("is_public_domain", False),
            credit_line=data.get("credit_line"),
            department_title=data.get("department_title"),
            artwork_type_title=data.get("artwork_type_title"),
            style_title=data.get("style_title"),
            classification_title=data.get("classification_title"),
            place_of_origin=data.get("place_of_origin"),
            description=data.get("description"),
            alt_image_ids=data.get("alt_image_ids", []),
        )

    def get_iiif_url(
        self,
        size: str = "full",
        image_id: str | None = None,
    ) -> str | None:
        """
        Get the IIIF Image API URL for this artwork.

        Args:
            size: IIIF size parameter. Options:
                - "full" or "max": Full resolution
                - "!800,800": Fit within 800x800 box
                - "843,": Width of 843, height proportional
                - ",400": Height of 400, width proportional
                - "pct:50": 50% of original size
            image_id: Specific image ID to use (defaults to primary image_id)

        Returns:
            IIIF URL string or None if no image available
        """
        img_id = image_id or self.image_id
        if not img_id:
            return None

        # Normalize "full" to "max" for IIIF 3.0 compatibility
        if size == "full":
            size = "max"

        # IIIF URL format: {base}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
        return f"{IIIF_BASE_URL}{img_id}/full/{size}/0/default.jpg"

    def get_all_image_urls(self, size: str = "full") -> list[str]:
        """Get IIIF URLs for all images of this artwork."""
        urls = []
        if self.image_id:
            url = self.get_iiif_url(size=size)
            if url:
                urls.append(url)
        for alt_id in self.alt_image_ids:
            url = self.get_iiif_url(size=size, image_id=alt_id)
            if url:
                urls.append(url)
        return urls


@dataclass
class SearchResult:
    """Search results from the API."""

    artworks: list[Artwork]
    total: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        """Check if there are more results to fetch."""
        return self.offset + len(self.artworks) < self.total


class ArticClient:
    """Client for the Art Institute of Chicago API."""

    def __init__(self, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ArticPythonClient/1.0",
            "Accept": "application/json",
        })
        self.timeout = timeout

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a GET request to the API."""
        url = urljoin(BASE_URL, endpoint)
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def search_artworks(
        self,
        query: str,
        size: int = 10,
        offset: int = 0,
        fields: list[str] | None = None,
    ) -> SearchResult:
        """
        Search for artworks by text query.

        Args:
            query: Search query (e.g., "classical art", "monet", "impressionism")
            size: Number of results to return (max 100)
            offset: Starting offset for pagination
            fields: Specific fields to return (None for all)

        Returns:
            SearchResult with matching artworks
        """
        # Default fields that are useful for most use cases
        default_fields = [
            "id",
            "title",
            "artist_display",
            "date_display",
            "medium_display",
            "dimensions",
            "image_id",
            "thumbnail",
            "is_public_domain",
            "credit_line",
            "department_title",
            "artwork_type_title",
            "style_title",
            "classification_title",
            "place_of_origin",
            "description",
            "alt_image_ids",
        ]

        params = {
            "q": query,
            "size": min(size, 100),
            "from": offset,
            "fields": ",".join(fields or default_fields),
        }

        data = self._request("artworks/search", params)

        artworks = [
            Artwork.from_api_response(item)
            for item in data.get("data", [])
        ]

        pagination = data.get("pagination", {})

        return SearchResult(
            artworks=artworks,
            total=pagination.get("total", 0),
            offset=pagination.get("offset", offset),
            limit=pagination.get("limit", size),
        )

    def get_artwork(self, artwork_id: int) -> Artwork:
        """
        Get a single artwork by ID.

        Args:
            artwork_id: The artwork's unique identifier

        Returns:
            Artwork object
        """
        data = self._request(f"artworks/{artwork_id}")
        return Artwork.from_api_response(data.get("data", {}))

    def download_image(
        self,
        artwork: Artwork,
        output_path: str | Path,
        size: str = "max",
        image_id: str | None = None,
    ) -> Path:
        """
        Download an artwork image via IIIF.

        Args:
            artwork: The artwork to download the image for
            output_path: Directory or file path for the downloaded image
            size: IIIF size parameter:
                - "max": Full resolution (default)
                - "!800,800": Fit within 800x800 box
                - "843,": Width of 843, height proportional
                - ",400": Height of 400, width proportional
                - "pct:50": 50% of original size
            image_id: Specific image ID (defaults to artwork's primary image)

        Returns:
            Path to the downloaded image

        Raises:
            ValueError: If the artwork has no image
            requests.HTTPError: If download fails
        """
        url = artwork.get_iiif_url(size=size, image_id=image_id)
        if not url:
            raise ValueError(f"Artwork {artwork.id} has no image")

        output_path = Path(output_path)

        # If output_path is a directory, generate filename
        if output_path.is_dir() or not output_path.suffix:
            output_path.mkdir(parents=True, exist_ok=True)
            img_id = image_id or artwork.image_id
            output_path = output_path / f"{artwork.id}_{img_id}.jpg"

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        output_path.write_bytes(response.content)
        return output_path

    def download_all_images(
        self,
        artwork: Artwork,
        output_dir: str | Path,
        size: str = "max",
    ) -> list[Path]:
        """
        Download all images for an artwork.

        Args:
            artwork: The artwork to download images for
            output_dir: Directory to save images
            size: IIIF size parameter

        Returns:
            List of paths to downloaded images
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = []

        # Download primary image
        if artwork.image_id:
            path = self.download_image(
                artwork,
                output_dir / f"{artwork.id}_{artwork.image_id}.jpg",
                size=size,
            )
            paths.append(path)

        # Download alternate images
        for i, alt_id in enumerate(artwork.alt_image_ids):
            path = self.download_image(
                artwork,
                output_dir / f"{artwork.id}_{alt_id}.jpg",
                size=size,
                image_id=alt_id,
            )
            paths.append(path)

        return paths


def search(query: str, limit: int = 10) -> list[Artwork]:
    """
    Convenience function to search for artworks.

    Args:
        query: Search query string
        limit: Maximum number of results

    Returns:
        List of matching Artwork objects
    """
    client = ArticClient()
    result = client.search_artworks(query, size=limit)
    return result.artworks


def download(artwork: Artwork, output_path: str | Path, size: str = "max") -> Path:
    """
    Convenience function to download an artwork image.

    Args:
        artwork: Artwork to download
        output_path: Where to save the image
        size: IIIF size parameter

    Returns:
        Path to downloaded image
    """
    client = ArticClient()
    return client.download_image(artwork, output_path, size=size)
