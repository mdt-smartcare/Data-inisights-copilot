from pydantic import BaseModel
from typing import Optional

class PromptGenerationRequest(BaseModel):
    data_dictionary: str

class PromptPublishRequest(BaseModel):
    prompt_text: str
    user_id: str

class PromptResponse(BaseModel):
    id: int
    prompt_text: str
    version: int
    is_active: int
