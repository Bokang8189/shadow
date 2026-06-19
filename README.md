# Personal AI Agent

A hybrid local-first AI agent with a web dashboard UI, powered by Ollama (local LLMs) and optionally connected to cloud APIs (Claude, GPT-4, Gemini).

---

## Quick Start

```bash
# 1. Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh   # Linux/Mac
# Windows: download from https://ollama.com

# 2. Pull a model
ollama pull deepseek-coder:7b   # best for coding (~4 GB)
ollama pull phi3:mini            # lightweight, fast (~2 GB)

# 3. Launch the agent
chmod +x start.sh
./start.sh

# 4. Open the dashboard
open frontend/index.html        # or double-click it in Finder/Explorer
```

---

## Project Structure

```
aurum-agent/
├── backend/
│   ├── main.py            ← FastAPI backend (Ollama bridge + API)
│   └── requirements.txt   ← Python dependencies
├── frontend/
│   └── index.html         ← Full dashboard UI (no build step needed)
├── start.sh               ← One-command launcher
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Backend + Ollama status |
| GET | `/status` | Full status with models and logs |
| GET | `/models` | List local Ollama models |
| POST | `/models/pull` | Pull a model (streamed progress) |
| DELETE | `/models/{name}` | Delete a model |
| POST | `/chat` | Single-turn chat (stream or full) |
| POST | `/chat/conversation` | Multi-turn chat with history |
| POST | `/agent/run` | Run a task via Open Interpreter |
| POST | `/keys` | Save a cloud API key (session only) |
| GET | `/metrics` | System metrics |
| GET | `/logs` | Tail backend logs |
| DELETE | `/logs` | Clear logs |

---

## Recommended Models

| Model | RAM needed | Best for |
|-------|-----------|----------|
| `deepseek-coder:7b` | 16 GB | Code generation, debugging |
| `phi3:mini` | 8 GB | Fast responses, general tasks |
| `llama3:8b` | 16 GB | Strong general reasoning |
| `mistral:7b` | 16 GB | Instruction following |
| `codellama:7b` | 16 GB | Code (alternative to DeepSeek) |

---

## Optional: Open Interpreter (Agent Tasks)

Install to enable the `/agent/run` endpoint, which lets the AI execute code, manage files, and build apps autonomously:

```bash
pip install open-interpreter
```

Then use the `/agent/run` endpoint or the "Agent Tasks" section in the dashboard.

---

## Optional: Cloud API Keys

Add keys via the Cloud APIs panel in the dashboard, or set environment variables before starting:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."
python backend/main.py
```

Keys are stored in the server session only and never written to disk.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API URL |
| `DEFAULT_MODEL` | `deepseek-coder:7b` | Default model for chat |

---

## Troubleshooting

**"Cannot connect to Ollama"** — Run `ollama serve` in a terminal, or install Ollama from https://ollama.com

**"No models found"** — Pull one: `ollama pull deepseek-coder:7b`

**"Backend not reachable"** — Start the backend: `cd backend && python main.py`

**Chat is slow** — Use a smaller model like `phi3:mini`, or ensure your machine has enough RAM.
