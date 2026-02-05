#!/bin/bash

#######################################
# AI Day Trader - Stop Script
#######################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BACKEND_PORT=8000
FRONTEND_PORT=5173

echo -e "${YELLOW}"
echo "=============================================="
echo "       AI Day Trader - Stopping...           "
echo "=============================================="
echo -e "${NC}"

# Kill by PID files if they exist
if [ -f /tmp/ai-trader-backend.pid ]; then
    PID=$(cat /tmp/ai-trader-backend.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "Stopping backend (PID: $PID)..."
        kill $PID 2>/dev/null || true
    fi
    rm -f /tmp/ai-trader-backend.pid
fi

if [ -f /tmp/ai-trader-frontend.pid ]; then
    PID=$(cat /tmp/ai-trader-frontend.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "Stopping frontend (PID: $PID)..."
        kill $PID 2>/dev/null || true
    fi
    rm -f /tmp/ai-trader-frontend.pid
fi

# Also kill anything on the ports (in case PIDs are stale)
echo "Clearing port $BACKEND_PORT..."
lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true

echo "Clearing port $FRONTEND_PORT..."
lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

# Clean up log files
rm -f /tmp/ai-trader-backend.log /tmp/ai-trader-frontend.log

echo ""
echo -e "${GREEN}AI Day Trader stopped.${NC}"
echo ""
