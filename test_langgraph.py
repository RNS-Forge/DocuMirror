import asyncio
from backend.app.agent_orchestrator import AgentOrchestrator

async def main():
    print("Testing LangGraph Workflow...")
    orchestrator = AgentOrchestrator()
    result = await orchestrator.process_document("test_image.jpg")
    print(f"Workflow result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
