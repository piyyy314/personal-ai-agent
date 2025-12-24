# Personal AI Agent (minimal LangChain example)

This project contains a minimal personal AI agent using LangChain + OpenAI.

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

Quick start (local, CLI)
1. Create project folder and copy files from this repo.
2. Create and activate a virtual environment:
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate      # Windows
3. Install deps:
   pip install -r requirements.txt
4. Copy `.env.example` to `.env` and add your keys.
5. Run:
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
2. Run (must set env vars in host or docker run):
   docker run --env-file .env -it personal-ai-agent:latest

Security & privacy
- Do not commit `.env` or secrets to source control.
- For higher privacy, swap the LLM wrapper to a local model (e.g., LlamaCPP) and remove cloud API keys.
- Avoid adding tools that run arbitrary shell commands unless you add strict safeguards.

Next steps / Enhancements
- Persistent memory (Chroma/Weaviate)
- RAG indexing personal documents
- Gradio/Streamlit web UI with auth
- Scheduler/background tasks

If you want, I can:
- Provide a version that uses a local LLM (llama.cpp) instead of OpenAI.
- Create a GitHub repo with these files and return a direct downloadable zip.
