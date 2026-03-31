"""Agents module: Agent management, configuration, and RBAC.

Module structure:
- models.py: SQLAlchemy ORM models (AgentModel, UserAgentModel, SystemPromptModel, PromptConfigModel)
- repository.py: Data access layer
- service.py: Business logic
- schemas.py: Pydantic request/response models
- routes.py: Agent management endpoints (28 endpoints)
"""