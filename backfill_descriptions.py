#!/usr/bin/env python3
"""
Backfill descriptions for saved artworks that don't have them.

Usage:
    python backfill_descriptions.py
"""

import json
import os
import sys
from pathlib import Path

from artic_client import ArticClient

# Configuration - matches app.py
DATA_DIR = Path(os.environ.get("ARTSY_DATA_DIR", "data"))
STATE_FILE = DATA_DIR / "state.json"


def main():
    if not STATE_FILE.exists():
        print(f"State file not found: {STATE_FILE}")
        sys.exit(1)

    # Load state
    with open(STATE_FILE) as f:
        state = json.load(f)

    saved_artworks = state.get("saved_artworks", [])
    if not saved_artworks:
        print("No saved artworks found.")
        return

    # Find artworks missing descriptions
    missing = [a for a in saved_artworks if not a.get("description")]
    if not missing:
        print("All saved artworks already have descriptions.")
        return

    print(f"Found {len(missing)} artwork(s) missing descriptions.")

    client = ArticClient()
    updated = 0

    for artwork in missing:
        artwork_id = artwork["id"]
        title = artwork.get("title", "Unknown")
        print(f"  Fetching description for: {title} (ID: {artwork_id})...", end=" ")

        try:
            full_artwork = client.get_artwork(artwork_id)
            if full_artwork.description:
                artwork["description"] = full_artwork.description
                updated += 1
                print("OK")
            else:
                print("No description available")
        except Exception as e:
            print(f"Error: {e}")

    if updated > 0:
        # Save updated state
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nUpdated {updated} artwork(s) with descriptions.")
    else:
        print("\nNo descriptions were added.")


if __name__ == "__main__":
    main()
