#!/usr/bin/env python3
"""
Builds a LangChain agent with privacy-aware caching and low-footprint execution.
"""
import os
from typing import Any

from dotenv import load_dotenv

from monitoring import record_cache_event, record_stealth_request, set_cache_entries
from performance import (
    PerformanceTunedAgent,
    PrivacyAwareResponseCache,
    get_validated_env_int,
)

load_dotenv()

try:
    # LangChain imports
    from langchain.agents import AgentType, Tool, initialize_agent
    from langchain.chains import LLMMathChain
    from langchain.memory import ConversationBufferWindowMemory
    from langchain_community.utilities import SerpAPIWrapper
    from langchain_openai import OpenAI
except Exception as e:
    raise ImportError("Missing dependencies. Run: pip install -r requirements.txt") from e

DEFAULT_MEMORY_WINDOW_TURNS = 6


def _build_tools(llm: Any) -> list[Any]:
    """Build the reusable tool list for the hosted OpenAI-backed agent."""
    tools = []

    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        serp = SerpAPIWrapper()
        tools.append(
            Tool(
                name="Search",
                func=serp.run,
                description="Useful for when you need to look up current web results.",
            )
        )

    llm_math = LLMMathChain.from_llm(llm=llm)
    tools.append(
        Tool(
            name="Calculator",
            func=llm_math.run,
            description="Performs multi-step math calculations.",
        )
    )
    return tools


def _build_agent_executor(memory_enabled: bool) -> Any:
    """Construct an agent executor with optional bounded conversation memory."""
    llm = OpenAI(temperature=0, max_tokens=800)
    tools = _build_tools(llm)
    memory = None
    if memory_enabled:
        memory = ConversationBufferWindowMemory(
            k=get_validated_env_int(
                "AGENT_MEMORY_WINDOW", DEFAULT_MEMORY_WINDOW_TURNS, minimum=1
            ),
            memory_key="chat_history",
            return_messages=True,
        )

    return initialize_agent(
        tools,
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=False,
    )


def create_agent() -> Any:
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment (see .env.example)")

    response_cache = PrivacyAwareResponseCache(
        max_entries=get_validated_env_int("AGENT_CACHE_MAX_ENTRIES", 128),
        ttl_seconds=get_validated_env_int("AGENT_CACHE_TTL_SECONDS", 300),
        on_event=record_cache_event,
        on_size_change=set_cache_entries,
    )
    return PerformanceTunedAgent(
        primary_agent=_build_agent_executor(memory_enabled=True),
        stealth_agent_factory=lambda: _build_agent_executor(memory_enabled=False),
        response_cache=response_cache,
        on_cache_event=record_cache_event,
        on_stealth_request=record_stealth_request,
    )
