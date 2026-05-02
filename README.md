# Personal AI Agent (minimal LangChain example)

This project contains a minimal personal AI agent using LangChain + OpenAI with optional FastAPI service, metrics, and alerting.

## 🚀 Ways to Run

### Option 1: FastAPI service (production-ready, monitored)
- Requires OpenAI key (or swap LLM implementation).
- Exposes `/v1/chat`, `/healthz`, and `/metrics` for Prometheus.

### Option 2: Cloud-Based CLI (OpenAI)
Uses OpenAI API - easy to set up but requires API key and sends data to cloud.

### Option 3: 100% Local & Private (Ollama) ⭐ RECOMMENDED
✅ **Completely private** - no data leaves your computer  
✅ **No restrictions** - use uncensored open-source models  
✅ **No API costs** - free to run 24/7  
✅ **Works offline** - no internet needed after setup

👉 **[See SETUP_LOCAL.md for full local setup guide](SETUP_LOCAL.md)**


Features
- Conversational memory (in-process)
- Optional web search via SerpAPI
- Calculator tool (LLM Math Chain)
- CLI loop for local use
- Dockerfile for containerized runs
- Script to create a zip archive for easy sharing

Requirements
- Python 3.8+
- pip
- If using OpenAI: OPENAI_API_KEY
- (Optional) SERPAPI_API_KEY for web search
- (Optional) Docker

Quick start (FastAPI service)
1. Create project folder and copy files from this repo.
2. Create and activate a virtual environment:
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate      # Windows
3. Install deps:
   pip install -r requirements.txt
4. Copy `.env.example` to `.env` and add your keys (set `API_AUTH_TOKEN` to enable auth).
5. Run the API:
   uvicorn server:app --host 0.0.0.0 --port 8000
6. Test:
   curl -H "x-api-key: $API_AUTH_TOKEN" -H "Content-Type: application/json" -d '{"prompt":"hello"}' http://localhost:8000/v1/chat

CLI mode
   python main.py

Create downloadable ZIP
- Linux / macOS:
  chmod +x create_zip.sh
  ./create_zip.sh
  -> personal-ai-agent.zip created

- Cross-platform Python:
  python create_zip.py
  -> personal-ai-agent.zip created

Docker (optional)
1. Build:
   docker build -t personal-ai-agent:latest .
2. Run API (must set env vars in host or docker run):
   docker run --env-file .env -p 8000:8000 personal-ai-agent:latest

Security, monitoring & privacy
- Do not commit `.env` or secrets to source control.
- Set `API_AUTH_TOKEN` to enforce API-key auth; rotate when incidents occur.
- Prometheus/Loki/Grafana stack included under `deploy/` with alert rules for downtime, error rate, slow P95, and suspicious access.
- For higher privacy, swap the LLM wrapper to a local model (e.g., LlamaCPP) and remove cloud API keys.
- Avoid adding tools that run arbitrary shell commands unless you add strict safeguards.

Production deployment
- Use the provided monitored stack: see `deploy/PRODUCTION.md` and `deploy/docker-compose.prod.yml`.
- Metrics are at `/metrics`, health at `/healthz`, and structured logs ship to Loki via Promtail.

Next steps / Enhancements
- Persistent memory (Chroma/Weaviate)
- RAG indexing personal documents
- Gradio/Streamlit web UI with auth
- Scheduler/background tasks

If you want, I can:
- Provide a version that uses a local LLM (llama.cpp) instead of OpenAI.
- Create a GitHub repo with these files and return a direct downloadable zip.
