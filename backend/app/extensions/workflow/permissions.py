"""Workflow permission constants.

Maps workflow API actions to permission strings that can be checked
by the auth middleware. These reuse the existing project/approval
permission namespace.
"""

# Workflow definition permissions
WORKFLOW_LIST = "project:list"
WORKFLOW_CREATE = "project:create"
WORKFLOW_READ = "project:read"
WORKFLOW_UPDATE = "project:update"
WORKFLOW_DELETE = "project:delete"
WORKFLOW_VALIDATE = "project:read"

# Workflow execution permissions
WORKFLOW_START = "project:advance"
WORKFLOW_STATUS = "project:read"
WORKFLOW_SIGNAL = "project:advance"
WORKFLOW_CANCEL = "project:advance"

# Source traceability permissions
SOURCE_READ = "chapter:view_all"
SOURCE_PARSE = "chapter:edit"

# Review permissions
REVIEW_ASSIGN = "approval:submit"
REVIEW_ACTION = "approval:review"
REVIEW_VIEW = "approval:view"
