#!/usr/bin/env python3
"""
CLI entrypoint for the personal AI agent with basic monitoring.
Run: python main.py
"""
import os

from dotenv import load_dotenv

from agent import create_agent
from health_server import start_health_server
from monitoring import (
    audit_event,
    configure_logging,
    detect_suspicious_query,
    record_request_outcome,
    record_security_event,
    set_session_status,
    timer,
)

STEALTH_PREFIX = "/stealth "


def main():
    load_dotenv()
    configure_logging()
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    start_health_server(port=health_port)
    set_session_status(True)
    audit_event("startup", {"mode": "cli"})

    agent = create_agent()
    print("Personal AI agent started. Type 'exit' to quit.")
    print("Use '/stealth your prompt' for a low-footprint request.")
    while True:
        try:
            query = input("\nYou: ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit"):
                print("Goodbye.")
                break
            stealth = False
            if query.startswith(STEALTH_PREFIX):
                stealth = True
                query = query[len(STEALTH_PREFIX) :].strip()
                if not query:
                    continue

            suspicious = detect_suspicious_query(query)
            if suspicious:
                record_security_event(suspicious)
                audit_event("suspicious_query", {"pattern": suspicious})

            start_time = timer()
            try:
                result = agent.invoke({"input": query, "stealth": stealth})
                response = result["output"]
                duration = timer() - start_time
                record_request_outcome("success", duration, source="cli")
                audit_event(
                    "response",
                    {
                        "latency_ms": round(duration * 1000, 2),
                        "status": "success",
                        "stealth": stealth,
                        "cache_hit": bool(result.get("cache_hit")),
                    },
                )
                if result.get("cache_hit"):
                    print("\nAgent [cache]:", response)
                    continue
                print("\nAgent:", response)
            except Exception as run_error:
                duration = timer() - start_time
                record_request_outcome("error", duration, source="cli")
                record_security_event("agent_error")
                audit_event(
                    "response",
                    {
                        "latency_ms": round(duration * 1000, 2),
                        "status": "error",
                        "error": str(run_error),
                    },
                )
                raise
        except KeyboardInterrupt:
            print("\nInterrupted. Exiting.")
            break
        except Exception as e:
            print("\nError:", e)
    audit_event("shutdown", {"mode": "cli"})
    set_session_status(False)


if __name__ == "__main__":
    main()
