"""Signal name constants for the DynamicGraphWorkflow.

These names must match exactly between the workflow signal handlers
and any external signal emitters (API routes, other workflows, tests).
"""

SIGNAL_PHASE_COMPLETE = "phase_complete"
SIGNAL_REVIEW_ACTION = "review_action"
SIGNAL_AI_COMPLETE = "ai_complete"
