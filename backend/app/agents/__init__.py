"""
Vitar AI Core — Growth Agents

Internal Celery-task-based agents powering Vitar's own growth (not a
customer-facing feature): Lead Hunter, Sales Agent, Content Agent,
Customer Success. Each agent's task module lives in this package; shared
infrastructure (AI provider, notifications, run logging, dry-run) lives in
app/services/ and app/agents/utils.py.
"""
