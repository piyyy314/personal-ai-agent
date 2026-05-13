#!/usr/bin/env python3
"""
Local AI agent using Ollama with bounded memory and privacy-aware caching.
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
    from langchain.agents import AgentType, Tool, initialize_agent
    from langchain.chains import LLMMathChain
    from langchain.memory import ConversationBufferWindowMemory
    from langchain_community.llms import Ollama
except Exception as e:
    raise ImportError("Missing dependencies. Run: pip install -r requirements_local.txt") from e

DEFAULT_MEMORY_WINDOW_TURNS = 6


def _build_tools(llm: Any) -> list[Any]:
    """Build the reusable tool list for the Ollama-backed local agent."""
    llm_math = LLMMathChain.from_llm(llm=llm)
    return [
        Tool(
            name="Calculator",
            func=llm_math.run,
            description="Performs multi-step math calculations.",
        )
    ]


def _build_agent_executor(memory_enabled: bool) -> Any:
    """Construct a local agent executor with optional bounded memory."""
    model_name = os.getenv("OLLAMA_MODEL", "qwen2:7b")
    llm = Ollama(
        model=model_name,
        temperature=0.2,
        base_url="http://localhost:11434",
    )
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
        _build_tools(llm),
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=False,
        handle_parsing_errors=True,
    )


def create_agent() -> Any:
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
