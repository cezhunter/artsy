"""
Art Display App - Flask Server

Interactive art display for Raspberry Pi with mobile control interface.
"""

import json
import os
import random
import shutil
import threading
import time
from pathlib import Path
from queue import Queue

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from artic_client import ArticClient, Artwork

app = Flask(__name__)

# Configuration - data directory can be set via ARTSY_DATA_DIR environment variable
DATA_DIR = Path(os.environ.get("ARTSY_DATA_DIR", "data"))
IMAGES_DIR = DATA_DIR / "images"
TEMP_DIR = DATA_DIR / "temp"
STATE_FILE = DATA_DIR / "state.json"

# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

print(f"Data directory: {DATA_DIR.absolute()}")

# SSE clients
sse_clients: list[Queue] = []

# Lock for thread-safe state access
state_lock = threading.Lock()

# API client
api_client = ArticClient()

# Current artwork in discover mode (not yet saved)
current_discover_artwork: Artwork | None = None
current_discover_image_path: Path | None = None


def get_default_state() -> dict:
    """Return default app state."""
    return {
        "mode": "discover",
        "timer_seconds": 30,
        "search_query": "impressionism",
        "paused": False,
        "rotation": 0,
        "seen_artwork_ids": [],
        "saved_artworks": [],
        "current_search_offset": 0,
        "display_history": [],
        "display_index": 0,
    }


def load_state() -> dict:
    """Load state from JSON file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
                # Ensure all keys exist
                default = get_default_state()
                for key in default:
                    if key not in state:
                        state[key] = default[key]
                return state
        except (json.JSONDecodeError, IOError):
            pass
    return get_default_state()


def save_state(state: dict) -> None:
    """Save state to JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def broadcast_update(event_type: str, data: dict | None = None) -> None:
    """Send SSE update to all connected clients."""
    message = {"type": event_type}
    if data:
        message["data"] = data

    event_data = f"data: {json.dumps(message)}\n\n"

    dead_clients = []
    for client in sse_clients:
        try:
            client.put_nowait(event_data)
        except:
            dead_clients.append(client)

    for client in dead_clients:
        sse_clients.remove(client)


def get_current_artwork_info(state: dict) -> dict | None:
    """Get info about the currently displayed artwork."""
    global current_discover_artwork

    if state["mode"] == "discover":
        if current_discover_artwork:
            return {
                "id": current_discover_artwork.id,
                "title": current_discover_artwork.title,
                "artist_display": current_discover_artwork.artist_display,
                "date_display": current_discover_artwork.date_display,
                "place_of_origin": current_discover_artwork.place_of_origin,
                "image_url": f"/api/image/temp" if current_discover_image_path else None,
            }
    else:  # display mode
        if state["saved_artworks"] and state["display_history"]:
            idx = state["display_index"] % len(state["display_history"])
            artwork_id = state["display_history"][idx]
            for artwork in state["saved_artworks"]:
                if artwork["id"] == artwork_id:
                    return {
                        **artwork,
                        "image_url": f"/api/image/saved/{artwork['id']}",
                    }
    return None


def fetch_next_discover_artwork(state: dict) -> bool:
    """Fetch the next unseen artwork from the API."""
    global current_discover_artwork, current_discover_image_path

    # Clean up previous temp image
    if current_discover_image_path and current_discover_image_path.exists():
        current_discover_image_path.unlink()

    current_discover_artwork = None
    current_discover_image_path = None

    seen_ids = set(state["seen_artwork_ids"])
    query = state["search_query"]
    offset = state["current_search_offset"]

    max_attempts = 10
    for _ in range(max_attempts):
        try:
            result = api_client.search_artworks(query, size=20, offset=offset)

            if not result.artworks:
                # No more results, reset offset
                state["current_search_offset"] = 0
                return False

            for artwork in result.artworks:
                if artwork.id not in seen_ids and artwork.image_id:
                    # Found an unseen artwork with an image
                    try:
                        # Download to temp location
                        temp_path = TEMP_DIR / f"{artwork.id}_{artwork.image_id}.jpg"
                        api_client.download_image(artwork, temp_path, size="max")

                        current_discover_artwork = artwork
                        current_discover_image_path = temp_path
                        return True
                    except Exception as e:
                        print(f"Error downloading artwork {artwork.id}: {e}")
                        continue

            # All artworks in this batch were seen, try next batch
            offset += 20
            state["current_search_offset"] = offset

        except Exception as e:
            print(f"Error searching artworks: {e}")
            return False

    return False


def shuffle_display_history(state: dict) -> None:
    """Shuffle saved artworks for display mode."""
    artwork_ids = [a["id"] for a in state["saved_artworks"]]
    random.shuffle(artwork_ids)
    state["display_history"] = artwork_ids
    state["display_index"] = 0


# Routes

@app.route("/")
def control_panel():
    """Mobile control interface."""
    return render_template("control.html")


@app.route("/display")
def display():
    """Fullscreen artwork display for monitor."""
    return render_template("display.html")


@app.route("/api/state")
def get_state():
    """Get current app state."""
    with state_lock:
        state = load_state()
        artwork_info = get_current_artwork_info(state)
        return jsonify({
            "mode": state["mode"],
            "timer_seconds": state["timer_seconds"],
            "search_query": state["search_query"],
            "paused": state["paused"],
            "rotation": state["rotation"],
            "saved_count": len(state["saved_artworks"]),
            "current_artwork": artwork_info,
        })


@app.route("/api/events")
def sse_events():
    """Server-Sent Events endpoint for real-time updates."""
    def generate():
        q = Queue()
        sse_clients.append(q)
        try:
            # Send initial state
            with state_lock:
                state = load_state()
                artwork_info = get_current_artwork_info(state)
                initial = {
                    "type": "state",
                    "data": {
                        "mode": state["mode"],
                        "timer_seconds": state["timer_seconds"],
                        "search_query": state["search_query"],
                        "paused": state["paused"],
                        "rotation": state["rotation"],
                        "saved_count": len(state["saved_artworks"]),
                        "current_artwork": artwork_info,
                    }
                }
            yield f"data: {json.dumps(initial)}\n\n"

            while True:
                try:
                    data = q.get(timeout=30)
                    yield data
                except:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            if q in sse_clients:
                sse_clients.remove(q)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/mode", methods=["POST"])
def set_mode():
    """Switch between discover and display modes."""
    data = request.get_json() or {}
    new_mode = data.get("mode")

    if new_mode not in ("discover", "display"):
        return jsonify({"error": "Invalid mode"}), 400

    with state_lock:
        state = load_state()
        state["mode"] = new_mode
        state["paused"] = False

        if new_mode == "discover":
            # Fetch first artwork
            if not current_discover_artwork:
                fetch_next_discover_artwork(state)
        else:
            # Shuffle for display mode
            if state["saved_artworks"]:
                shuffle_display_history(state)

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("mode_change", {
        "mode": new_mode,
        "current_artwork": artwork_info,
    })

    return jsonify({"success": True, "mode": new_mode})


@app.route("/api/timer", methods=["POST"])
def set_timer():
    """Set timer interval in seconds."""
    data = request.get_json() or {}
    seconds = data.get("seconds")

    try:
        seconds = int(seconds)
        if seconds < 5:
            seconds = 5
        if seconds > 300:
            seconds = 300
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid timer value"}), 400

    with state_lock:
        state = load_state()
        state["timer_seconds"] = seconds
        save_state(state)

    broadcast_update("timer_change", {"timer_seconds": seconds})

    return jsonify({"success": True, "timer_seconds": seconds})


@app.route("/api/rotation", methods=["POST"])
def set_rotation():
    """Set image rotation (0, 90, 180, 270 degrees)."""
    data = request.get_json() or {}
    rotation = data.get("rotation")

    try:
        rotation = int(rotation)
        if rotation not in (0, 90, 180, 270):
            rotation = 0
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid rotation value"}), 400

    with state_lock:
        state = load_state()
        state["rotation"] = rotation
        save_state(state)

    broadcast_update("rotation_change", {"rotation": rotation})

    return jsonify({"success": True, "rotation": rotation})


def normalize_quotes(text: str) -> str:
    """Normalize smart/curly quotes to straight quotes for search."""
    # Smart double quotes to straight double quotes
    text = text.replace('”', '"').replace('“', '"')
    return text


@app.route("/api/query", methods=["POST"])
def set_query():
    """Set search query for discover mode."""
    data = request.get_json() or {}
    query = normalize_quotes(data.get("query", "").strip())

    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400

    with state_lock:
        state = load_state()
        state["search_query"] = query
        state["current_search_offset"] = 0  # Reset offset for new query

        # Fetch new artwork if in discover mode
        if state["mode"] == "discover":
            fetch_next_discover_artwork(state)

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("query_change", {
        "search_query": query,
        "current_artwork": artwork_info,
    })

    return jsonify({"success": True, "search_query": query})


@app.route("/api/save", methods=["POST"])
def save_artwork():
    """Save current artwork in discover mode."""
    global current_discover_artwork, current_discover_image_path

    with state_lock:
        state = load_state()

        if state["mode"] != "discover":
            return jsonify({"error": "Can only save in discover mode"}), 400

        if not current_discover_artwork or not current_discover_image_path:
            return jsonify({"error": "No artwork to save"}), 400

        artwork = current_discover_artwork

        # Move image to saved directory
        saved_path = IMAGES_DIR / current_discover_image_path.name
        shutil.move(str(current_discover_image_path), str(saved_path))

        # Add to saved artworks
        state["saved_artworks"].append({
            "id": artwork.id,
            "title": artwork.title,
            "artist_display": artwork.artist_display,
            "date_display": artwork.date_display,
            "place_of_origin": artwork.place_of_origin,
            "image_path": str(saved_path),
        })

        # Mark as seen
        state["seen_artwork_ids"].append(artwork.id)

        # Fetch next artwork
        current_discover_artwork = None
        current_discover_image_path = None
        fetch_next_discover_artwork(state)

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("artwork_saved", {
        "saved_count": len(state["saved_artworks"]),
        "current_artwork": artwork_info,
    })

    return jsonify({"success": True})


@app.route("/api/next", methods=["POST"])
def next_artwork():
    """Go to next artwork (dislike in discover, skip in display)."""
    global current_discover_artwork, current_discover_image_path

    with state_lock:
        state = load_state()

        if state["mode"] == "discover":
            # Dislike - mark as seen and skip
            if current_discover_artwork:
                state["seen_artwork_ids"].append(current_discover_artwork.id)

            # Clean up temp image
            if current_discover_image_path and current_discover_image_path.exists():
                current_discover_image_path.unlink()

            current_discover_artwork = None
            current_discover_image_path = None

            fetch_next_discover_artwork(state)
        else:
            # Display mode - go forward
            if state["display_history"]:
                state["display_index"] = (state["display_index"] + 1) % len(state["display_history"])

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("artwork_change", {"current_artwork": artwork_info})

    return jsonify({"success": True, "current_artwork": artwork_info})


@app.route("/api/prev", methods=["POST"])
def prev_artwork():
    """Go to previous artwork (display mode only)."""
    with state_lock:
        state = load_state()

        if state["mode"] != "display":
            return jsonify({"error": "Can only go back in display mode"}), 400

        if state["display_history"]:
            state["display_index"] = (state["display_index"] - 1) % len(state["display_history"])

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("artwork_change", {"current_artwork": artwork_info})

    return jsonify({"success": True, "current_artwork": artwork_info})


@app.route("/api/pause", methods=["POST"])
def toggle_pause():
    """Toggle pause state."""
    with state_lock:
        state = load_state()
        state["paused"] = not state["paused"]
        save_state(state)

    broadcast_update("pause_change", {"paused": state["paused"]})

    return jsonify({"success": True, "paused": state["paused"]})


@app.route("/api/delete", methods=["POST"])
def delete_artwork():
    """Delete current artwork in display mode."""
    with state_lock:
        state = load_state()

        if state["mode"] != "display":
            return jsonify({"error": "Can only delete in display mode"}), 400

        if not state["display_history"]:
            return jsonify({"error": "No artwork to delete"}), 400

        idx = state["display_index"] % len(state["display_history"])
        artwork_id = state["display_history"][idx]

        # Find and remove artwork
        for i, artwork in enumerate(state["saved_artworks"]):
            if artwork["id"] == artwork_id:
                # Delete image file
                image_path = Path(artwork["image_path"])
                if image_path.exists():
                    image_path.unlink()

                # Remove from saved artworks
                state["saved_artworks"].pop(i)
                break

        # Update display history
        state["display_history"].remove(artwork_id)

        # Adjust index if needed
        if state["display_history"]:
            state["display_index"] = state["display_index"] % len(state["display_history"])
        else:
            state["display_index"] = 0

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    broadcast_update("artwork_deleted", {
        "saved_count": len(state["saved_artworks"]),
        "current_artwork": artwork_info,
    })

    return jsonify({"success": True})


@app.route("/api/image/temp")
def get_temp_image():
    """Serve the current temp image in discover mode."""
    if current_discover_image_path and current_discover_image_path.exists():
        return send_from_directory(
            current_discover_image_path.parent,
            current_discover_image_path.name,
            mimetype="image/jpeg"
        )
    return "", 404


@app.route("/api/image/saved/<int:artwork_id>")
def get_saved_image(artwork_id: int):
    """Serve a saved artwork image."""
    with state_lock:
        state = load_state()

        for artwork in state["saved_artworks"]:
            if artwork["id"] == artwork_id:
                image_path = Path(artwork["image_path"])
                if image_path.exists():
                    return send_from_directory(
                        image_path.parent,
                        image_path.name,
                        mimetype="image/jpeg"
                    )
    return "", 404


@app.route("/api/init", methods=["POST"])
def init_app():
    """Initialize app state and load first artwork."""
    global current_discover_artwork, current_discover_image_path

    with state_lock:
        state = load_state()

        if state["mode"] == "discover":
            if not current_discover_artwork:
                fetch_next_discover_artwork(state)
        else:
            if state["saved_artworks"] and not state["display_history"]:
                shuffle_display_history(state)

        save_state(state)
        artwork_info = get_current_artwork_info(state)

    return jsonify({
        "success": True,
        "mode": state["mode"],
        "current_artwork": artwork_info,
    })


if __name__ == "__main__":
    # Initialize state on startup
    with state_lock:
        state = load_state()
        if state["mode"] == "discover":
            fetch_next_discover_artwork(state)
        elif state["saved_artworks"]:
            shuffle_display_history(state)
        save_state(state)

    # Run server
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
