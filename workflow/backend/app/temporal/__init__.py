"""Temporal execution-engine integration for the workflow platform.

The workflow API and the Temporal worker run in separate processes. Import
``app.temporal.client`` or ``app.temporal.worker`` explicitly; this package
initializer stays import-light so Temporal's workflow sandbox can import
``app.temporal.workflow`` without pulling in configuration or pathlib.
"""
