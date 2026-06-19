#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Personal AI Agent — Launch script
# Usage: ./start.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${BLUE}"
echo "  ██████╗ ███████╗██████╗ ███████╗ ██████╗ ███╗   ██╗ █████╗ ██╗"
echo "  ██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗████╗  ██║██╔══██╗██║"
echo "  ██████╔╝█████╗  ██████╔╝███████╗██║   ██║██╔██╗ ██║███████║██║"
echo "  ██╔═══╝ ██╔══╝  ██╔══██╗╚════██║██║   ██║██║╚██╗██║██╔══██║██║"
echo "  ██║     ███████╗██║  ██║███████║╚██████╔╝██║ ╚████║██║  ██║███████╗"
echo "  ╚═╝     ╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝"
echo "                            AI  A G E N T"
echo -e "${NC}"

# ── 1. Check Python ───────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ Python 3 not found. Install from https://python.org${NC}"; exit 1
fi
echo -e "${GREEN}✓ Python $(python3 --version)${NC}"

# ── 2. Check/start Ollama ─────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
  echo -e "${GREEN}✓ Ollama found${NC}"
  if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    echo -e "${YELLOW}⚡ Starting Ollama in background...${NC}"
    ollama serve &>/tmp/ollama.log &
    sleep 2
  fi
  echo -e "${GREEN}✓ Ollama running on http://localhost:11434${NC}"
else
  echo -e "${YELLOW}⚠  Ollama not found. Install from https://ollama.com${NC}"
  echo -e "   Continuing anyway — you can install it later."
fi

# ── 3. Install Python deps ────────────────────────────────────────────────────
echo -e "\n${BLUE}Installing backend dependencies...${NC}"
cd "$(dirname "$0")/backend"
pip install -r requirements.txt -q

# ── 4. Start backend ──────────────────────────────────────────────────────────
echo -e "\n${GREEN}Starting Personal AI Agent backend on http://localhost:8000${NC}"
echo -e "${BLUE}Open your browser to: ${NC}file://$(realpath ../frontend/index.html)"
echo -e "${YELLOW}Press Ctrl+C to stop.${NC}\n"

python3 main.py
