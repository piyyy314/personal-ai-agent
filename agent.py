#!/usr/bin/env python3
"""
Builds a LangChain agent with memory and a couple of tools.
Adjust LLM and tools here to match your privacy / capability needs.
"""
import os
import json
from dotenv import load_dotenv
from flight_analysis import analyze_flight_operations

load_dotenv()

try:
    # LangChain imports
    from langchain_openai import OpenAI
    from langchain.memory import ConversationBufferMemory
    from langchain.agents import initialize_agent, Tool, AgentType
    from langchain.chains import LLMMathChain
    from langchain_community.utilities import SerpAPIWrapper
except Exception as e:
    raise ImportError("Missing dependencies. Run: pip install -r requirements.txt") from e

def create_agent():
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment (see .env.example)")

    # LLM: you can swap this for a local LLM wrapper (LlamaCPP, Mistral local, etc.)
    llm = OpenAI(temperature=0, max_tokens=800)

    # Memory: short-term conversation buffer
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

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

    # Web search via SerpAPI (optional)
    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        serp = SerpAPIWrapper()
        tools.append(
            Tool(
                name="Search",
                func=serp.run,
                description="Useful for when you need to look up current web results."
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

    # Math tool (uses the LLM's math chain)
    llm_math = LLMMathChain.from_llm(llm=llm)
    tools.append(
        Tool(
            name="Calculator",
            func=llm_math.run,
            description="Performs multi-step math calculations."
        )
    )

    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=False,
    )
    return agent
