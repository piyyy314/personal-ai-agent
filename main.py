#!/usr/bin/env python3
"""
Minimal CLI for the personal AI agent.
Run: python main.py
"""
import os
import time
import uuid
from dotenv import load_dotenv
from agent import create_agent
from monitoring import logger, metrics, health
from health_server import start_health_server

def main():
    load_dotenv()

    # Start health check server
    health_server = start_health_server(port=int(os.getenv("HEALTH_PORT", 8080)))

    # Generate session ID for audit logging
    session_id = str(uuid.uuid4())

    logger.log_event(
        event_type="agent_startup",
        message="Personal AI agent starting",
        level="info",
        session_id=session_id
    )

    try:
        agent = create_agent()
        logger.log_event(
            event_type="agent_initialized",
            message="Agent successfully initialized",
            level="info",
            session_id=session_id
        )

        # Update metrics
        metrics.set_gauge("active_sessions", 1)

        print("Personal AI agent started. Type 'exit' to quit.")
        print(f"Health endpoint: http://localhost:{os.getenv('HEALTH_PORT', 8080)}/health")

        while True:
            try:
                query = input("\nYou: ").strip()
                if not query:
                    continue
                if query.lower() in ("exit", "quit"):
                    print("Goodbye.")
                    break

                # Track request metrics
                start_time = time.time()
                metrics.increment("requests_total")

                logger.audit_log(
                    action="query",
                    resource="agent",
                    outcome="started",
                    session_id=session_id,
                    query_length=len(query)
                )

                try:
                    response = agent.run(query)
                    elapsed = time.time() - start_time

                    # Record success metrics
                    metrics.increment("requests_success")
                    metrics.observe("response_time_seconds", elapsed)

                    logger.audit_log(
                        action="query",
                        resource="agent",
                        outcome="success",
                        session_id=session_id,
                        response_time=elapsed,
                        query_length=len(query),
                        response_length=len(response)
                    )

                    print("\nAgent:", response)

                except Exception as e:
                    elapsed = time.time() - start_time
                    metrics.increment("requests_failed")

                    logger.audit_log(
                        action="query",
                        resource="agent",
                        outcome="error",
                        session_id=session_id,
                        error=str(e),
                        response_time=elapsed
                    )

                    logger.log_event(
                        event_type="query_error",
                        message=f"Query failed: {str(e)}",
                        level="error",
                        session_id=session_id,
                        error=str(e)
                    )
                    print("\nError:", e)

            except KeyboardInterrupt:
                print("\nInterrupted. Exiting.")
                break

    except Exception as e:
        logger.log_event(
            event_type="agent_initialization_failed",
            message=f"Failed to initialize agent: {str(e)}",
            level="critical",
            session_id=session_id,
            error=str(e)
        )
        print(f"\nFatal error: {e}")
        raise

    finally:
        # Cleanup
        metrics.set_gauge("active_sessions", 0)
        logger.log_event(
            event_type="agent_shutdown",
            message="Personal AI agent shutting down",
            level="info",
            session_id=session_id
        )

if __name__ == "__main__":
    main()
