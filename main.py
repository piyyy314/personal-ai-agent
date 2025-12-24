#!/usr/bin/env python3
"""
Minimal CLI for the personal AI agent.
Run: python main.py
"""
import os
from dotenv import load_dotenv
from agent import create_agent

def main():
    load_dotenv()
    agent = create_agent()
    print("Personal AI agent started. Type 'exit' to quit.")
    while True:
        try:
            query = input("\nYou: ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit"):
                print("Goodbye.")
                break
            response = agent.run(query)
            print("\nAgent:", response)
        except KeyboardInterrupt:
            print("\nInterrupted. Exiting.")
            break
        except Exception as e:
            print("\nError:", e)

if __name__ == "__main__":
    main()
