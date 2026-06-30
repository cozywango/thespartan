import asyncio
import os
import sys

# Add the spartan directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from spartan.core.backend import OrnithBackend
from spartan.core.events import EventBus, EventType

async def main():
    backend = OrnithBackend(
        working_directory=os.getcwd(),
        system_prompt="STAGE: PASSIVE VULNERABILITY ASSESSMENT REPORT\n\nGenerate a report.",
        model="ornith:1.0",
        base_url="http://localhost:11434/v1",
    )
    
    await backend.connect()
    
    context = "A" * 15000  # Large context
    prompt = f"Here is the context:\n{context}\n\nGenerate the report."
    
    await backend.query(prompt)
    
    async for msg in backend.receive_messages():
        print(f"Message received: {msg.type} - {msg.content}")

if __name__ == "__main__":
    asyncio.run(main())
