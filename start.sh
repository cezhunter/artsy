#!/bin/bash
# Art Display App - Startup Script for Raspberry Pi Kiosk Mode
#
# Usage:
#   ./start.sh [options] [kiosk]
#
# Options:
#   --data-dir PATH    Set custom data directory (default: ./data)
#
# Examples:
#   ./start.sh                           - Start server with default data dir
#   ./start.sh --data-dir /mnt/usb/art   - Use custom data directory
#   ./start.sh --data-dir ~/art kiosk    - Custom data dir + kiosk mode
#
# To run on boot, add to /etc/rc.local or create a systemd service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
PORT=5000
DISPLAY_URL="http://localhost:$PORT/display"
VENV_DIR="$SCRIPT_DIR/venv"
DATA_DIR="$SCRIPT_DIR/data"

# Parse arguments
KIOSK_MODE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        kiosk)
            KIOSK_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./start.sh [--data-dir PATH] [kiosk]"
            exit 1
            ;;
    esac
done

# Export data directory for the Python app
export ARTSY_DATA_DIR="$DATA_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Art Display App${NC}"
echo "================================"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required${NC}"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies
if ! python3 -c "import flask; import requests" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r requirements.txt --quiet
fi

# Create data directories
mkdir -p "$DATA_DIR/images" "$DATA_DIR/temp"
echo "Data directory: $DATA_DIR"

# Function to start the Flask server
start_server() {
    echo -e "${GREEN}Starting Flask server on port $PORT...${NC}"
    python3 app.py &
    SERVER_PID=$!
    echo "Server PID: $SERVER_PID"

    # Wait for server to be ready
    echo "Waiting for server to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:$PORT/api/state" > /dev/null 2>&1; then
            echo -e "${GREEN}Server is ready!${NC}"
            return 0
        fi
        sleep 1
    done
    echo -e "${RED}Server failed to start${NC}"
    return 1
}

# Function to start Chromium in kiosk mode
start_kiosk() {
    echo -e "${GREEN}Starting Chromium in kiosk mode...${NC}"

    # Disable screen blanking
    if command -v xset &> /dev/null; then
        xset s off
        xset -dpms
        xset s noblank
    fi

    # Hide cursor
    if command -v unclutter &> /dev/null; then
        unclutter -idle 0 &
    fi

    # Start Chromium in kiosk mode
    if command -v chromium-browser &> /dev/null; then
        chromium-browser \
            --kiosk \
            --noerrdialogs \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --disable-restore-session-state \
            --no-first-run \
            --start-fullscreen \
            --password-store=basic \
            --autoplay-policy=no-user-gesture-required \
            "$DISPLAY_URL" &
    elif command -v chromium &> /dev/null; then
        chromium \
            --kiosk \
            --noerrdialogs \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --disable-restore-session-state \
            --no-first-run \
            --start-fullscreen \
            --password-store=basic \
            --autoplay-policy=no-user-gesture-required \
            "$DISPLAY_URL" &
    else
        echo -e "${YELLOW}Chromium not found. Opening in default browser...${NC}"
        if command -v xdg-open &> /dev/null; then
            xdg-open "$DISPLAY_URL" &
        fi
    fi
}

# Function to show access info
show_info() {
    echo ""
    echo "================================"
    echo -e "${GREEN}App is running!${NC}"
    echo ""
    echo "Display (for monitor):"
    echo "  http://localhost:$PORT/display"
    echo ""
    echo "Control Panel (for mobile):"

    # Get local IP addresses
    if command -v hostname &> /dev/null; then
        IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        if [ -n "$IP" ]; then
            echo "  http://$IP:$PORT/"
        fi
    fi
    echo "  http://localhost:$PORT/"
    echo ""
    echo "Press Ctrl+C to stop"
    echo "================================"
}

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null
    fi
    # Kill any child processes
    pkill -P $$ 2>/dev/null
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGINT SIGTERM

# Main execution
if [ "$KIOSK_MODE" = true ]; then
    start_server
    if [ $? -eq 0 ]; then
        start_kiosk
        show_info
        # Wait indefinitely
        wait
    fi
else
    start_server
    if [ $? -eq 0 ]; then
        show_info
        # Wait for server process
        wait $SERVER_PID
    fi
fi
