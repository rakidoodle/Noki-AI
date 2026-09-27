from free_agent.cli import registry_for
from free_agent.client import OpenRouterClient
from free_agent.config import load_settings
from free_agent.multi_agent.orchestrator import Orchestrator
from free_agent.runner import AgentRunner

settings = load_settings()
settings.require_api_key()
settings.prepare_workspace()
result = Orchestrator(AgentRunner(settings, OpenRouterClient(settings), registry_for(settings))).run(
    "Calculate 19 * 37 and explain the result.")
print(result.final_text)
