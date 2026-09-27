from ..agent import Agent

PLANNER = Agent(name="planner", instructions="Make a short, actionable plan. Do not use tools.")
WORKER = Agent(name="worker", instructions="Complete the task using tools only when useful. Report the result honestly.",
               tools=["calculator", "current_datetime", "list_workspace_files", "read_workspace_text", "write_workspace_text"])
REVIEWER = Agent(name="reviewer", instructions="Review the worker result. Reply OK if complete, otherwise state one concrete fix. Do not use tools.")
