from pydantic import BaseModel
from typing import Optional, Dict

class PromptGenerationRequest(BaseModel):
    data_dictionary: str
    # Schema selection could be passed here, but frontend currently packs it into data_dictionary for simplicity
    # or we can be explicit. The implementation plan says "accept schema_selection".
    # However, Step 345 (ConfigPage.tsx) does:
    # `const fullContext = schemaContext + dataDictionary;`
    # `await generateSystemPrompt(fullContext);`
    # So the frontend collapses it into `data_dictionary`.
    # I will stick to the current implementation where data_dictionary contains everything.
    # No changes needed here if we follow the frontend's lead, but to be robust for the future:
    # I won't change this model yet unless I refactor the frontend call.
    # The prompt says "Update `generate_draft_prompt` to accept selected schema". 
    # The frontend is sending it AS TEXT in `data_dictionary`.
    # I will rely on that for now to avoid breaking the just-written frontend.


class PromptPublishRequest(BaseModel):
    prompt_text: str
    user_id: str
    connection_id: Optional[int] = None
    schema_selection: Optional[str] = None # JSON string
    data_dictionary: Optional[str] = None
    reasoning: Optional[str] = None # JSON string
    example_questions: Optional[str] = None  # JSON string list
    embedding_config: Optional[str] = None # JSON string
    retriever_config: Optional[str] = None # JSON string

class PromptResponse(BaseModel):
    id: int
    prompt_text: str
    version: str

    is_active: int
    reasoning: Optional[Dict[str, str]] = None  # New field for explainability
    created_at: Optional[str] = None
    created_by_username: Optional[str] = None
    embedding_config: Optional[str] = None
    retriever_config: Optional[str] = None
