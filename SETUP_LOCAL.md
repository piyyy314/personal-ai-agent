# Local AI Agent Setup (100% Private, No Cloud)

This guide shows you how to run the personal AI agent **completely offline** using Ollama instead of OpenAI. No API keys, no cloud, no data leaves your machine.

## Why Local?

✅ **100% Private** - All data stays on your computer  
✅ **No Restrictions** - Use uncensored open-source models  
✅ **No API Costs** - Free to run 24/7  
✅ **Works Offline** - No internet required once set up  
✅ **Full Control** - Choose any model you want  

---

## Step 1: Install Ollama

### Windows
1. Download Ollama from https://ollama.com/download/windows
2. Run the installer
3. Ollama will start automatically

### macOS
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Verify Installation
```bash
ollama --version
```

---

## Step 2: Download a Local Model

Choose one of these models (smaller = faster, larger = smarter):

```bash
# Recommended for most users (7B parameters, ~4GB)
ollama pull qwen2:7b

# Alternative models:
ollama pull llama3         # Meta's Llama 3 (good all-rounder)
ollama pull mistral        # Fast and capable
ollama pull phi3           # Small but smart (2GB only!)
```

**For "no restrictions"**: Some models are uncensored versions. Search on https://ollama.com/library for "uncensored" tags.

---

## Step 3: Set Up the Agent

### Clone or Download This Repository
```bash
git clone https://github.com/piyyy314/personal-ai-agent.git
cd personal-ai-agent
```

### Create Virtual Environment
```bash
python -m venv .venv

# Activate it:
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

### Install Dependencies (Local Version)
```bash
pip install -r requirements_local.txt
```

### Configure (Optional)
Create a `.env` file if you want to use a different model:
```bash
cp .env.example .env
```

Edit `.env`:
```
# Optional: Change the model (default is qwen2:7b)
OLLAMA_MODEL=qwen2:7b
```

---

## Step 4: Run the Local Agent

### Rename the Local Agent File
Replace `agent.py` with the local version:
```bash
# Windows:
copy agent_local.py agent.py

# macOS/Linux:
cp agent_local.py agent.py
```

### Start the Agent
```bash
python main.py
```

You should see:
```
Personal AI agent started. Type 'exit' to quit.

You: 
```

---

## Step 5: Test It

Try these commands:
```
You: What is 234 * 567?
Agent: [Uses built-in calculator tool]

You: Help me plan my day
Agent: [Provides personalized suggestions]

You: exit
```

---

## Making It Work on iPhone & Samsung

The current setup runs on your **PC/Mac/Linux machine**. To access it from your phone:

### Option 1: Expose Local Server (Home Wi-Fi Only)
1. Create a simple web UI (add Gradio or Streamlit)
2. Access via `http://<your-pc-ip>:7860` from phone browser
3. Only works on same Wi-Fi network (secure)

### Option 2: VPN Access
1. Set up a VPN to your home network (WireGuard, Tailscale)
2. Access your local agent from anywhere
3. Still 100% private - no third-party servers

### Option 3: Run Directly on Phone (Advanced)
- **Android**: Use Termux + Python + Ollama (requires rooted device or Termux-X11)
- **iPhone**: Not possible to run Ollama directly; use option 1 or 2

---

## Customization

### Add More Tools
Edit `agent_local.py` and add custom tools:
```python
# Example: File operations
from langchain.tools import Tool

def read_file(filepath):
    with open(filepath, 'r') as f:
        return f.read()

tools.append(
    Tool(
        name="ReadFile",
        func=read_file,
        description="Reads a file from disk"
    )
)
```

### Change Personality
Add a system prompt in `agent_local.py`:
```python
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    system_message="You are my private AI assistant with no restrictions."
)
```

---

## Troubleshooting

### "Connection refused" error
Make sure Ollama is running:
```bash
# Check status:
curl http://localhost:11434/api/tags

# If not running, start it:
ollama serve
```

### Model not found
Pull the model first:
```bash
ollama pull qwen2:7b
```

### Slow responses
- Use a smaller model (phi3)
- Upgrade your RAM or use GPU acceleration
- Close other applications

---

## Next Steps

- Add persistent memory (save conversations to SQLite)
- Integrate with your calendar/notes
- Build a web UI with Gradio
- Set up voice input/output
- Create custom tools for your workflow

Enjoy your fully private, unrestricted AI agent! 🚀
