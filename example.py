#!/usr/bin/env python3
"""
Example usage of the Art Institute of Chicago API client.

This script demonstrates searching for artworks and downloading images.
"""

from pathlib import Path

from artic_client import ArticClient, search, download


def main():
    # Initialize client
    client = ArticClient()

    # Example 1: Simple search using convenience function
    print("=" * 60)
    print("Example 1: Search for 'classical art'")
    print("=" * 60)

    artworks = search("classical art", limit=5)
    for art in artworks:
        print(f"\n{art.title}")
        print(f"  Artist: {art.artist_display or 'Unknown'}")
        print(f"  Date: {art.date_display or 'Unknown'}")
        print(f"  Type: {art.artwork_type_title or 'Unknown'}")
        print(f"  Has image: {art.image_id is not None}")
        if art.image_id:
            print(f"  IIIF URL: {art.get_iiif_url()}")

    # Example 2: Search with pagination
    print("\n" + "=" * 60)
    print("Example 2: Paginated search for 'impressionism'")
    print("=" * 60)

    result = client.search_artworks("impressionism", size=3, offset=0)
    print(f"\nFound {result.total} total results")
    print(f"Showing {len(result.artworks)} results (offset={result.offset})")
    print(f"Has more: {result.has_more}")

    for art in result.artworks:
        print(f"  - {art.title} ({art.date_display})")

    # Example 3: Get a specific artwork by ID
    print("\n" + "=" * 60)
    print("Example 3: Get specific artwork (Starry Night - ID 27992)")
    print("=" * 60)

    try:
        artwork = client.get_artwork(27992)  # La Grande Jatte
        print(f"\nTitle: {artwork.title}")
        print(f"Artist: {artwork.artist_display}")
        print(f"Date: {artwork.date_display}")
        print(f"Medium: {artwork.medium_display}")
        print(f"Dimensions: {artwork.dimensions}")
        print(f"Public Domain: {artwork.is_public_domain}")
        print(f"Credit: {artwork.credit_line}")
        if artwork.description:
            print(f"Description: {artwork.description[:200]}...")
    except Exception as e:
        print(f"Error fetching artwork: {e}")

    # Example 4: Download an image
    print("\n" + "=" * 60)
    print("Example 4: Download image")
    print("=" * 60)

    # Find a public domain artwork with an image
    result = client.search_artworks("monet water lilies", size=5)
    public_artworks = [a for a in result.artworks if a.is_public_domain and a.image_id]

    if public_artworks:
        artwork = public_artworks[0]
        print(f"\nDownloading: {artwork.title}")
        print(f"Artist: {artwork.artist_display}")

        # Create downloads directory
        output_dir = Path("downloads")
        output_dir.mkdir(exist_ok=True)

        # Download at different sizes
        sizes = {
            "thumbnail": "!200,200",
            "medium": "!800,800",
            "full": "max",
        }

        for name, size in sizes.items():
            try:
                path = client.download_image(
                    artwork,
                    output_dir / f"{artwork.id}_{name}.jpg",
                    size=size,
                )
                print(f"  Downloaded {name}: {path} ({path.stat().st_size:,} bytes)")
            except Exception as e:
                print(f"  Error downloading {name}: {e}")
    else:
        print("No public domain artworks with images found in search results")

    # Example 5: IIIF URL generation for different sizes
    print("\n" + "=" * 60)
    print("Example 5: IIIF URL formats")
    print("=" * 60)

    if artworks and artworks[0].image_id:
        art = artworks[0]
        print(f"\nArtwork: {art.title}")
        print(f"Image ID: {art.image_id}")
        print("\nIIIF URLs for different sizes:")
        print(f"  Full resolution: {art.get_iiif_url('max')}")
        print(f"  Fit in 800x800:  {art.get_iiif_url('!800,800')}")
        print(f"  Width 400px:     {art.get_iiif_url('400,')}")
        print(f"  Height 300px:    {art.get_iiif_url(',300')}")
        print(f"  50% scale:       {art.get_iiif_url('pct:50')}")


if __name__ == "__main__":
    main()
