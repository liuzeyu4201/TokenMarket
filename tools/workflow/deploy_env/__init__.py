"""Deploy stack lifecycle (ADR 003 Layer D).

Public entry: ``make deploy`` / ``make deploy-down`` with ``mode=test|prod``.
"""

from .lifecycle import deploy_down, deploy_up

__all__ = ["deploy_up", "deploy_down"]
