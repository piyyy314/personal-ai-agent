#!/usr/bin/env python3
"""
Local AI agent using Ollama (no cloud, fully private).
Swap this in place of agent.py if you want to run without OpenAI.
"""
import os
import json
from dotenv import load_dotenv
from flight_analysis import analyze_flight_operations

load_dotenv()

try:
    from langchain_community.llms import Ollama
    from langchain.memory import ConversationBufferMemory
    from langchain.agents import initialize_agent, Tool, AgentType
    from langchain.chains import LLMMathChain
except Exception as e:
    raise ImportError("Missing dependencies. Run: pip install -r requirements_local.txt") from e


def create_agent():
    """
    Creates an agent using a local Ollama model.
    No API keys required - fully private and offline.
    """
    # Use local Ollama model (install Ollama first: https://ollama.com)
    # Popular models: qwen2:7b, llama3, mistral, phi3
    model_name = os.getenv("OLLAMA_MODEL", "qwen2:7b")
    
    # LLM: runs locally on your machine
    llm = Ollama(
        model=model_name,
        temperature=0.2,
        base_url="http://localhost:11434"  # default Ollama endpoint
    )
    
    # Memory: conversation buffer
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )
    
    # Tools
    tools = []

    def run_flight_analysis(payload: str) -> str:
        """Analyze flight and event intelligence data from a JSON payload."""
        parsed = json.loads(payload)
        result = analyze_flight_operations(
            flights=parsed.get("flights") or [],
            events=parsed.get("events") or [],
            filters=parsed.get("filters") or {},
            search_query=parsed.get("search_query"),
            search_limit=int(parsed.get("search_limit") or 10),
        )
        return json.dumps(result, indent=2, sort_keys=True)
    
    # Math tool
    llm_math = LLMMathChain.from_llm(llm=llm)
    tools.append(
        Tool(
            name="Calculator",
            func=llm_math.run,
            description="Performs multi-step math calculations."
        )
    )

    tools.append(
        Tool(
            name="FlightIntel",
            func=run_flight_analysis,
            description=(
                "Analyze flight and event datasets for advanced filtering, search, "
                "threat signals, and stealth overlays. Input must be JSON with "
                "flights, optional events, optional filters, and optional search_query."
            ),
        )
    )
    
    # You can add more local tools here:
    # - File system operations (read/write notes)
    # - Calendar/task management
    # - Local document search/RAG
    
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=False,
        handle_parsing_errors=True,
    )
    
    return agent
