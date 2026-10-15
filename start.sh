#!/bin/bash

#######################################
# AI Day Trader - Startup Script
# Run from project root: ./start.sh
#######################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ports
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}"
echo "=============================================="
echo "       AI Day Trader - Startup Script        "
echo "=============================================="
echo -e "${NC}"

#######################################
# Helper Functions
#######################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        log_warn "Killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

#######################################
# Pre-flight Checks
#######################################

echo ""
log_info "Running pre-flight checks..."

# Check required commands
check_command python3
check_command node
check_command npm

log_success "All required commands available"

# Check if .env exists
if [ ! -f ".env" ]; then
    log_error ".env file not found. Copy .env.example to .env and fill in your keys."
    echo "  Required keys: ALPACA_API_KEY, ALPACA_SECRET_KEY, ANTHROPIC_API_KEY"
    exit 1
fi
log_success ".env file found"

# Check if venv exists
if [ ! -d "venv" ]; then
    log_warn "Virtual environment not found. Creating..."
    python3 -m venv venv
    log_success "Virtual environment created"
fi

#######################################
# Kill Existing Processes
#######################################

echo ""
log_info "Cleaning up existing processes..."

kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT

log_success "Ports $BACKEND_PORT and $FRONTEND_PORT cleared"

#######################################
# Activate Virtual Environment
#######################################

echo ""
log_info "Activating virtual environment..."

source venv/bin/activate

if [ -z "$VIRTUAL_ENV" ]; then
    log_error "Failed to activate virtual environment"
    exit 1
fi

log_success "Virtual environment activated"

#######################################
# Install/Update Python Dependencies
#######################################

echo ""
log_info "Checking Python dependencies..."

# Check if requirements need updating
pip install --quiet --upgrade pip

# Everything the engine and the API need, pinned in requirements.txt
pip install --quiet -r requirements.txt || {
    log_warn "Some packages may need manual installation"
}

log_success "Python dependencies ready"

#######################################
# Install/Update Frontend Dependencies
#######################################

echo ""
log_info "Checking frontend dependencies..."

cd dashboard

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    log_info "Installing frontend dependencies (first time)..."
    npm install --silent
else
    # Quick check for updates
    npm install --silent 2>/dev/null || true
fi

cd ..

log_success "Frontend dependencies ready"

#######################################
# Test API Connections
#######################################

echo ""
log_info "Testing API connections..."

# Quick connection test
python3 -c "
import sys
sys.path.insert(0, '.')
from config.settings import get_settings
settings = get_settings()

# Check Alpaca
if not settings.alpaca.api_key:
    print('ERROR: ALPACA_API_KEY not set')
    sys.exit(1)

# Check Anthropic
if not settings.anthropic.api_key:
    print('ERROR: ANTHROPIC_API_KEY not set')
    sys.exit(1)

print('API keys configured')
" 2>/dev/null || {
    log_error "API keys not properly configured in .env"
    exit 1
}

log_success "API keys verified"

#######################################
# Start Backend Server
#######################################

echo ""
log_info "Starting backend server on port $BACKEND_PORT..."

# Start uvicorn in background
nohup ./venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port $BACKEND_PORT --reload > /tmp/ai-trader-backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Check if backend is running
if ! curl -s http://127.0.0.1:$BACKEND_PORT/health > /dev/null 2>&1; then
    # Wait a bit more
    sleep 2
    if ! curl -s http://127.0.0.1:$BACKEND_PORT/health > /dev/null 2>&1; then
        log_error "Backend failed to start. Check /tmp/ai-trader-backend.log"
        cat /tmp/ai-trader-backend.log | tail -20
        exit 1
    fi
fi

log_success "Backend running (PID: $BACKEND_PID)"

#######################################
# Start Frontend Server
#######################################

echo ""
log_info "Starting frontend server on port $FRONTEND_PORT..."

cd dashboard

# Start vite in background
nohup npm run dev -- --port $FRONTEND_PORT > /tmp/ai-trader-frontend.log 2>&1 &
FRONTEND_PID=$!

cd ..

# Wait for frontend to start
sleep 3

# Check if frontend is running
if ! curl -s http://127.0.0.1:$FRONTEND_PORT > /dev/null 2>&1; then
    sleep 2
    if ! curl -s http://127.0.0.1:$FRONTEND_PORT > /dev/null 2>&1; then
        log_warn "Frontend may still be starting..."
    fi
fi

log_success "Frontend running (PID: $FRONTEND_PID)"

#######################################
# Open Browser
#######################################

echo ""
log_info "Opening dashboard in browser..."

sleep 1

# Open browser (macOS)
if command -v open &> /dev/null; then
    open "http://localhost:$FRONTEND_PORT"
# Linux
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:$FRONTEND_PORT"
fi

#######################################
# Done
#######################################

echo ""
echo -e "${GREEN}=============================================="
echo "           AI Day Trader Started!            "
echo "==============================================${NC}"
echo ""
echo "  Dashboard:  http://localhost:$FRONTEND_PORT"
echo "  API:        http://localhost:$BACKEND_PORT"
echo "  API Docs:   http://localhost:$BACKEND_PORT/docs"
echo ""
echo "  Backend log:  /tmp/ai-trader-backend.log"
echo "  Frontend log: /tmp/ai-trader-frontend.log"
echo ""
echo -e "${YELLOW}To stop:${NC} ./stop.sh (or kill ports $BACKEND_PORT and $FRONTEND_PORT)"
echo ""

# Save PIDs for stop script
echo "$BACKEND_PID" > /tmp/ai-trader-backend.pid
echo "$FRONTEND_PID" > /tmp/ai-trader-frontend.pid

echo -e "${BLUE}Servers are running in the background.${NC}"
echo -e "${BLUE}View logs with: tail -f /tmp/ai-trader-backend.log /tmp/ai-trader-frontend.log${NC}"
echo ""
