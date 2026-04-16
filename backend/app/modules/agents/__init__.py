"""
Agents module: Agent management and configurations.

Module structure:
- models.py: SQLAlchemy ORM models
  - AgentModel: Core agent entity
  - AgentConfigModel: Versioned agent configurations
  - UserAgentModel: RBAC for agent access

- repository.py: Data access layer
  - AgentRepository: Agent CRUD
  - AgentConfigRepository: Config versioning
  - UserAgentRepository: Access control

- service.py: Business logic
  - AgentService: Agent management with access control
  - AgentConfigService: Config versioning and updates
  - UserAgentService: RBAC operations

- schemas.py: Pydantic request/response models
- routes.py: API endpoints for agents and configs

Note: Data sources are in app.modules.data_sources
"""
from app.modules.agents.models import (
    AgentModel, AgentConfigModel, UserAgentModel
)
from app.modules.agents.routes import router

__all__ = [
    "AgentModel",
    "AgentConfigModel",
    "UserAgentModel",
    "router",
]