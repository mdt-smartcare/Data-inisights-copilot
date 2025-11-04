# --- Standard Library Imports ---
import os
import re
import json
import yaml
import uuid  # <-- CHANGE 1: Import uuid
from typing import List, Dict, Any, Tuple, Optional, Generator, TypedDict, Annotated, Sequence, Literal
import operator
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gradio as gr
import gradio_client.utils
from dotenv import load_dotenv
import traceback # <-- Import for error logging

# --- ML/Embeddings Imports ---
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity

# --- LangChain Core Imports ---
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.output_parsers.json import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field # <-- CHANGE 2: Import Pydantic
from langchain_openai import ChatOpenAI

# --- LangChain Community/Integrations ---
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent

# --- NEW: LANGGRAPH IMPORTS (STEP 4) ---
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode # Use ToolNode as fixed before
from langgraph.checkpoint.memory import MemorySaver

# --- NEW: GRAPH RAG IMPORTS (STEP 3) ---
from langchain_neo4j import Neo4jGraph # Use correct import as fixed before
from langchain.chains import GraphCypherQAChain

# --- NEW: 1. IMPORT LANGFUSE ---
from langfuse.langchain import CallbackHandler

# --- Local/Project Imports ---
from src.rag.retrieve import AdvancedRAGRetriever

# --- 1. CONFIGURATION ---

load_dotenv()

class Config:
    """Centralized configuration for the application."""
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    DB_USER: str = "admin"
    DB_PASSWORD: str = "admin"
    DB_NAME: str = "Spice_BD"
    DB_URI: str = f"postgresql://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"
    
    NEO4J_URI: Optional[str] = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: Optional[str] = os.getenv("NEO4J_USER", "admin") # Match your .env
    NEO4J_PASSWORD: Optional[str] = os.getenv("NEO4J_PASSWORD", "admin") # Match your .env
    
    EMBEDDING_MODEL_PATH: str = "./models/bge-m3"
    LLM_MODEL: str = "gpt-4o"
    LLM_FAST_MODEL: str = "gpt-4o-mini"
    FEEDBACK_LOG_FILE: str = "feedback_log.csv"
    
    LANGFUSE_PUBLIC_KEY: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_HOST: Optional[str] = os.getenv("LANGFUSE_HOST")
    
    USERS: Dict[str, str] = {
        "admin": "admin",
        "analyst": "analyst2024",
        "viewer": "view123"
    }

if not Config.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found or is empty in your .env file.")
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

if not Config.NEO4J_PASSWORD:
    print("Warning: NEO4J_PASSWORD not found in .env. Graph RAG tool will fail.")

# --- 2. AGENT AND TOOL SETUP ---

class LocalHuggingFaceEmbeddings(Embeddings):
    def __init__(self, model_id: str):
        self.model = SentenceTransformer(model_id)
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()
    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()

print("Initializing agent components...")
llm = ChatOpenAI(temperature=0, model_name=Config.LLM_MODEL)
fast_llm = ChatOpenAI(temperature=0, model_name=Config.LLM_FAST_MODEL)
embedding_model = LocalHuggingFaceEmbeddings(model_id=Config.EMBEDDING_MODEL_PATH)

# --- Tool 1: SQL AGENT (The "Counter") ---
db = SQLDatabase.from_uri(Config.DB_URI)
sql_agent = create_sql_agent(llm=llm, db=db, agent_type="openai-tools", verbose=True)

# --- Tool 2: RAG RETRIEVER (The "Finder") ---
with open("config/embedding_config.yaml", 'r') as f:
    rag_config = yaml.safe_load(f)
rag_retriever = AdvancedRAGRetriever(config=rag_config)

# --- Tool 3: GRAPH RAG (The "Connector") (STEP 3) ---
try:
    graph = Neo4jGraph(
        url=Config.NEO4J_URI,
        username=Config.NEO4J_USER,
        password=Config.NEO4J_PASSWORD
    )
    graph.refresh_schema()
    graph_qa_chain = GraphCypherQAChain.from_llm(
        cypher_llm=llm,
        qa_llm=fast_llm,
        graph=graph,
        verbose=True
    )
    print("Neo4j Graph RAG tool initialized.")
except Exception as e:
    print(f"Warning: Could not initialize Neo4j Graph. Tool will be unavailable. Error: {e}")
    graph_qa_chain = None

# --- AGENT TOOLS LIST ---
tools: List[Tool] = [
    Tool(
        name="database_query_agent", 
        func=sql_agent.invoke, 
        description="""... (your existing description) ..."""
    ),
    Tool(
        name="semantic_patient_search", 
        func=rag_retriever.invoke,
        description="""... (your existing description) ..."""
    ),
]

# Define tool names for the Pydantic model
tool_names: list[str] = ["database_query_agent", "semantic_patient_search"]

if graph_qa_chain:
    tools.append(
        Tool(
            name="knowledge_graph_search",
            func=graph_qa_chain.invoke,
            description="""... (your existing description) ..."""
        )
    )
    tool_names.append("knowledge_graph_search")

# Use ToolNode as fixed before
tool_executor = ToolNode(tools)

# --- 4. SELF-REFLECTIVE AGENT (LANGGRAPH) (STEP 4) ---

# --- Agent Prompt ---
agent_prompt = ChatPromptTemplate.from_messages([
    ("system", """... (your existing system prompt) ..."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])


# <-- CHANGE 3: Define Pydantic models for structured output -->
# This replaces `with_structured_output(AIMessage)` and fixes the BadRequestError
class ToolCall(BaseModel):
    name: Literal[tuple(tool_names)] # Use the dynamic list of tool names
    args: dict = Field(description="The arguments for the tool.")

class AgentOutput(BaseModel):
    tool_calls: List[ToolCall] = Field(description="A list of tool calls to execute.")
# <-- END CHANGE 3 -->


# Bind the tools to the LLM for the agent node
# We now output the AgentOutput Pydantic model and specify method="function_calling"
agent_runnable = agent_prompt | llm.with_structured_output(
    AgentOutput, 
    method="function_calling"
)

# --- Critique Prompt ---
critique_prompt = ChatPromptTemplate.from_messages([
    ("system", """... (your existing critique prompt) ..."""),
])
critique_chain = critique_prompt | fast_llm.with_structured_output(JsonOutputParser)

# --- Generation Prompt ---
generation_prompt = ChatPromptTemplate.from_messages([
    ("system", """... (your existing generation prompt) ..."""),
    ("user", "My question was: {input}"),
    ("user", "Here is the information you found:\n\n{context}"),
])
generation_chain = generation_prompt | llm

# --- LangGraph State Definition ---
class AgentState(TypedDict):
    input: str
    chat_history: Sequence[BaseMessage]
    agent_scratchpad: list[BaseMessage]
    intermediate_steps: Annotated[list[tuple[AIMessage, List[ToolMessage]]], operator.add]
    generation: str
    critique_result: dict
    trace_id: Optional[str]

# --- LangGraph Nodes ---

# <-- CHANGE 4: Update call_agent_node -->
def call_agent_node(state: AgentState) -> dict:
    """The 'router' - decides which tool to call."""
    logger.info("---CALLING AGENT---")
    agent_scratchpad = state.get('agent_scratchpad', [])
    
    # Invoke the agent to get the AgentOutput Pydantic object
    agent_output: AgentOutput = agent_runnable.invoke({
        "input": state["input"],
        "chat_history": state["chat_history"],
        "agent_scratchpad": agent_scratchpad
    })
    
    # Convert the Pydantic object into an AIMessage with tool_calls
    # This is what the ToolNode expects
    tool_calls = []
    if agent_output.tool_calls:
        for tc in agent_output.tool_calls:
            tool_calls.append({
                "id": f"tool_call_{str(uuid.uuid4())[:8]}", # Generate a unique ID
                "name": tc.name,
                "args": tc.args
            })
    
    agent_outcome_message = AIMessage(content="", tool_calls=tool_calls)
    return {"agent_scratchpad": [agent_outcome_message]}
# <-- END CHANGE 4 -->


def call_tools_node(state: AgentState) -> dict:
    """Executes the tools chosen by the agent."""
    logger.info("---CALLING TOOLS---")
    tool_call_msg = state['agent_scratchpad'][-1]
    
    if not isinstance(tool_call_msg, AIMessage) or not tool_call_msg.tool_calls:
        logger.warning("No tool call found in agent outcome. Skipping tool execution.")
        # This is a failure case, let's add a message to the scratchpad
        error_msg = HumanMessage(content="No tool was called. Please generate a final answer based on this fact.")
        return {"agent_scratchpad": [error_msg]}

    tool_messages = []
    for tool_call in tool_call_msg.tool_calls:
        try:
            tool_output = tool_executor.invoke(tool_call)
            tool_messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call['id']))
        except Exception as e:
            logger.error(f"Error executing tool {tool_call['name']}: {e}")
            tool_messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=tool_call['id']))
            
    return {
        "agent_scratchpad": tool_messages,
        "intermediate_steps": [(tool_call_msg, tool_messages)]
    }

def generate_answer_node(state: AgentState) -> dict:
    """Generates the final answer based on all context."""
    logger.info("---GENERATING ANSWER---")
    context = ""
    for agent_msg, tool_msgs in state["intermediate_steps"]:
        context += f"Agent thought: {agent_msg.content}\n"
        for tool_msg in tool_msgs:
            context += f"Tool Output: {tool_msg.content}\n\n"
            
    # If no tools were called, context will be empty.
    if not context:
        context = "No information was retrieved."
            
    generation = generation_chain.invoke({"input": state["input"], "context": context}).content
    return {"generation": generation}

def critique_answer_node(state: AgentState) -> dict:
    """Critiques the generated answer."""
    logger.info("---CRITIQUING ANSWER---")
    context = ""
    for agent_msg, tool_msgs in state["intermediate_steps"]:
        for tool_msg in tool_msgs:
            context += f"{tool_msg.content}\n"
            
    critique_result = critique_chain.invoke({
        "context": context,
        "generation": state["generation"]
    })
    logger.info(f"Critique result: {critique_result}")
    return {"critique_result": critique_result}

# --- LangGraph Edges (Conditional Logic) ---

def should_call_tools(state: AgentState) -> str:
    """Decides if the agent's last message was a tool call or a final answer."""
    last_msg = state['agent_scratchpad'][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "call_tools"
    # If no tool call, or if it's a ToolMessage/HumanMessage, we generate
    return "generate"

def should_retry(state: AgentState) -> str:
    """Decides to finish or retry based on critique."""
    # Check if 'critique' key exists and is 'yes'
    if state.get("critique_result", {}).get("critique") == "yes":
        logger.info("Critique passed. Finishing.")
        return "end"
    else:
        critique_reason = state.get("critique_result", {}).get("reason", "No reason provided.")
        logger.warning(f"Critique failed: {critique_reason}. Retrying.")
        # Add the critique as a human message to force the agent to reconsider
        retry_msg = HumanMessage(
            content=f"Your last answer was not good. Critique: {critique_reason}. Please try again, perhaps with a different tool or strategy."
        )
        # We add to the scratchpad, not replace it
        new_scratchpad = state["agent_scratchpad"] + [retry_msg]
        return {
            "agent_scratchpad": new_scratchpad,
            # We clear intermediate steps to force a new path
            "intermediate_steps": [] 
        }

# --- Build the Graph ---
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_agent_node)
workflow.add_node("tools", call_tools_node)
workflow.add_node("generate", generate_answer_node)
workflow.add_node("critique", critique_answer_node)

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_call_tools,
    {
        "call_tools": "tools",
        "generate": "generate",
    }
)
# After tools, we decide again. The tool output might need another tool call.
# This makes the agent more robust.
workflow.add_edge("tools", "agent") 
workflow.add_edge("generate", "critique") 

workflow.add_conditional_edges(
    "critique",
    should_retry,
    {
        "end": END,
        "retry": "agent"
    }
)

# Add memory
checkpointer = MemorySaver()

# Compile the final, stateful, self-correcting agent
main_agent_executor = workflow.compile(checkpointer=checkpointer)
print("--- FHIR RAG Self-Correcting Agent is Ready ---")


# --- 5. HELPER AND LOGGING FUNCTIONS ---
# (No changes to: create_plotly_chart, log_feedback, authenticate_user, 
#  get_embedding_info, create_embedding_visualization, enhanced_rag_search)
# ...
def create_plotly_chart(chart_json: Dict[str, Any]) -> Optional[go.Figure]:
    try:
        title = chart_json.get("title", "Chart")
        chart_type = chart_json.get("type", "bar")
        data = chart_json.get("data", {})
        labels, values = data.get("labels", []), data.get("values", [])
        if not labels or not values: return None
        if chart_type == "pie":
            fig = px.pie(names=labels, values=values, title=title)
        else:
            fig = px.bar(x=labels, y=values, title=title)
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
        return fig
    except Exception as e:
        print(f"Error creating plotly chart: {e}")
        return None

def format_thinking_process(intermediate_steps: List[Tuple[Any, Any]]) -> str:
    log = "### Agent Thinking Process\n\n"
    if not intermediate_steps: 
        return log + "No intermediate steps."
    
    for action, observations in intermediate_steps:
        log += f"**Thought (Tool Call):**\n"
        if not action.tool_calls:
             log += f"```\n{action.content}\n```\n"
             continue
            
        for tool_call in action.tool_calls:
            log += f"**Tool:** `{tool_call['name']}`\n"
            log += f"**Input:**\n```json\n{json.dumps(tool_call['args'], indent=2)}\n```\n\n"
        
        for obs in observations:
            log += f"**Output:**\n```\n{obs.content}\n```\n---\n"
    return log

def log_feedback(query: str, suggestions_json: str, selected_index: int, rating: float, trace_id: str) -> gr.update:
    try:
        if not query or not suggestions_json or selected_index is None:
            return gr.update(value="Could not log feedback: Missing context.", visible=True)
        suggestions_list = json.loads(suggestions_json)
        selected_question = suggestions_list[int(selected_index)]
        feedback_data = {"timestamp": [pd.Timestamp.now()], "query": [query], "suggested_question": [selected_question], "rating": [rating], "trace_id": [trace_id]}
        df = pd.DataFrame(feedback_data)
        file_exists = os.path.isfile(Config.FEEDBACK_LOG_FILE)
        df.to_csv(Config.FEEDBACK_LOG_FILE, mode='a', header=not file_exists, index=False)
        return gr.update(value=f"Feedback logged (Rating: {rating})", visible=True)
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return gr.update(value="Error logging feedback.", visible=True)

def authenticate_user(username: str, password: str) -> Tuple[bool, str]:
    if not username or not password:
        return False, "Please enter both username and password"
    if username in Config.USERS and Config.USERS[username] == password:
        return True, f"Welcome, {username}!"
    else:
        return False, "Invalid username or password"
def get_embedding_info(query: str) -> Dict[str, Any]:
    try:
        query_embedding = embedding_model.embed_query(query)
        embedding_stats = {
            "model_name": "BAAI/bge-m3", "dimensions": len(query_embedding),
            "vector_norm": float(np.linalg.norm(query_embedding)),
            "vector_mean": float(np.mean(query_embedding)), "vector_std": float(np.std(query_embedding)),
            "vector_min": float(np.min(query_embedding)), "vector_max": float(np.max(query_embedding))
        }
        vector_sample = [round(float(x), 3) for x in query_embedding[:10]]
        return {"query": query, "embedding_stats": embedding_stats, "vector_sample": vector_sample, "full_vector": query_embedding}
    except Exception as e:
        return {"error": f"Failed to generate embedding: {str(e)}"}

def create_embedding_visualization(query: str, retrieved_docs_with_scores: Optional[List[Tuple[Document, float]]] = None) -> Dict[str, Any]:
    try:
        query_embedding = np.array(embedding_model.embed_query(query))
        if retrieved_docs_with_scores and len(retrieved_docs_with_scores) > 0:
            retrieved_docs = [doc for doc, score in retrieved_docs_with_scores]
            reranker_scores = [score for doc, score in retrieved_docs_with_scores]
            doc_texts = [doc.page_content[:200] for doc in retrieved_docs[:5]]
            doc_embeddings = [embedding_model.embed_query(text) for text in doc_texts]
            all_embeddings = np.array([query_embedding] + doc_embeddings)
            pca = PCA(n_components=2)
            embeddings_2d = pca.fit_transform(all_embeddings)
            similarities = reranker_scores[:5]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[embeddings_2d[0][0]], y=[embeddings_2d[0][1]], mode='markers',
                marker=dict(size=15, color='red', symbol='star'), name='Query',
                text=[f"Query: {query[:50]}..."], hovertemplate="<b>%{text}</b><extra></extra>"
            ))
            for i, (doc_text, similarity) in enumerate(zip(doc_texts, similarities)):
                fig.add_trace(go.Scatter(
                    x=[embeddings_2d[i+1][0]], y=[embeddings_2d[i+1][1]], mode='markers',
                    marker=dict(size=12, color=similarity, colorscale='Viridis', colorbar=dict(title="Re-Rank Score")),
                    name=f'Doc {i+1}', text=[f"Doc {i+1}: {doc_text[:50]}...<br>Re-Rank Score: {similarity:.3f}"],
                    hovertemplate="<b>%{text}</b><extra></extra>"
                ))
            fig.update_layout(title="Embedding Space Visualization (PCA 2D)", xaxis_title="PCA Component 1", yaxis_title="PCA Component 2", showlegend=True, height=400)
            return {"visualization": fig, "similarities": similarities, "doc_texts": doc_texts}
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=list(range(min(50, len(query_embedding)))), y=query_embedding[:50], name="Embedding Values"))
            fig.update_layout(title=f"Query Embedding Vector (First 50 dimensions)", xaxis_title="Dimension", yaxis_title="Value", height=300)
            return {"visualization": fig}
    except Exception as e:
        return {"error": f"Failed to create visualization: {str(e)}"}

def enhanced_rag_search(query: str) -> Dict[str, Any]:
    try:
        embedding_info = get_embedding_info(query)
        if "error" in embedding_info: return embedding_info
        retrieved_docs_with_scores = rag_retriever.retrieve_and_rerank_with_scores(query)
        viz_info = create_embedding_visualization(query, retrieved_docs_with_scores)
        docs_info = []
        for i, (doc, score) in enumerate(retrieved_docs_with_scores[:5]):
            docs_info.append({"index": i + 1, "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content, "metadata": doc.metadata, "reranker_score": score})
        return {"query": query, "embedding_info": embedding_info, "retrieved_docs": docs_info, "visualization": viz_info, "total_docs_found": len(retrieved_docs_with_scores)}
    except Exception as e:
        return {"error": f"Enhanced RAG search failed: {str(e)}"}


# --- 6. CORE AGENT AND UI LOGIC (RE-ARCHITECTED) ---

def get_agent_response(message: str, history: List[List[str]], current_user: str) -> Dict[str, Any]:
    """
    Runs the main LANGGRAPH agent and formats the output.
    """
    # 1. Initialize Langfuse handler
    local_langfuse_handler = CallbackHandler()
    trace_id = None
    
    # 2. Prepare chat history
    chat_history_messages = []
    for user_msg, ai_msg in history:
        chat_history_messages.append(HumanMessage(content=user_msg))
        chat_history_messages.append(AIMessage(content=ai_msg))

    # 3. Create a unique thread ID for memory
    thread_id = f"user_{current_user}_thread_{str(uuid.uuid4())[:8]}" # New thread per query
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # 4. Invoke the LangGraph agent
        result = main_agent_executor.invoke(
            {"input": message, "chat_history": chat_history_messages, "agent_scratchpad": []},
            config={"callbacks": [local_langfuse_handler], **config}
        )
        
        # 5. Get Trace ID
        if hasattr(local_langfuse_handler, 'last_trace_id'):
            trace_id = local_langfuse_handler.last_trace_id
        logger.info(f"Langfuse Trace ID: {trace_id}")

        # 6. Extract final state
        final_state = result
        full_response = final_state.get("generation", "An error occurred.")
        intermediate_steps = final_state.get("intermediate_steps", [])

        # 7. Get embedding analysis
        embedding_analysis = get_embedding_info(message)
        
        # 8. Check if semantic search was used
        semantic_search_used = False
        retrieved_docs_with_scores = []
        for action, observations in intermediate_steps:
            if action.tool_calls and any(tc['name'] == 'semantic_patient_search' for tc in action.tool_calls):
                semantic_search_used = True
                try:
                    retrieved_docs_with_scores = rag_retriever.retrieve_and_rerank_with_scores(message)
                except Exception as e:
                    print(f"Could not re-fetch docs for viz: {e}")
                break
        
        # 9. Create visualization
        viz_info = create_embedding_visualization(message, retrieved_docs_with_scores if semantic_search_used else None)
        
        # 10. Standardize output
        parsed_output = {
            "text_answer": full_response, "chart_figure": None, "suggested_questions": [], 
            "thinking_markdown": format_thinking_process(intermediate_steps),
            "embedding_info": embedding_analysis, "embedding_viz": viz_info.get("visualization", None),
            "semantic_search_used": semantic_search_used,
            "retrieved_docs_count": len(retrieved_docs_with_scores), "trace_id": trace_id
        }
        
        # 11. Parse JSON block
        json_match = re.search(r'```json\s*({.*?})\s*```', full_response, re.DOTALL)
        if json_match:
            try:
                response_data = json.loads(json_match.group(1))
                parsed_output["text_answer"] = full_response[:json_match.start()].strip()
                if chart_json := response_data.get("chart_json"):
                    parsed_output["chart_figure"] = create_plotly_chart(chart_json)
                if questions := response_data.get("suggested_questions"):
                    parsed_output["suggested_questions"] = questions
            except json.JSONDecodeError:
                print("Warning: Failed to parse JSON from agent response.")
                parsed_output["text_answer"] += " (Note: Visualization data was malformed)"
        
        return parsed_output

    except Exception as e:
        logger.critical(f"Error in LangGraph invocation: {e}", exc_info=True)
        if hasattr(local_langfuse_handler, 'last_trace_id'):
            trace_id = local_langfuse_handler.last_trace_id
        return {
            "text_answer": f"Sorry, a critical error occurred: {e}",
            "chart_figure": None, "suggested_questions": [],
            "thinking_markdown": f"## Critical Error\n\n```{e}\n\n{traceback.format_exc()}```",
            "embedding_info": {}, "embedding_viz": None, "semantic_search_used": False,
            "retrieved_docs_count": 0, "trace_id": trace_id
        }


def chat_ui_updater(message: str, history: List[List[str]], current_user: str) -> Generator[Tuple, None, None]:
    """
    Handles the chat UI updates.
    """
    if not history:
        history = []
    
    history.append([message, ""])
    
    # 1. First yield: Show "thinking"
    yield (
        history, 
        gr.update(visible=False),  # plot
        gr.update(value="*Agent is thinking... (Running self-correcting graph)*"),  # thinking_box
        gr.Dataframe(value=[]),  # suggestions_df
        gr.update(visible=False),  # suggestions_box
        "",  # textbox
        gr.Textbox(value=message),  # last_query
        gr.Textbox(),  # suggestions_store
        gr.State(""), # current_trace_id_store
        gr.update(value={}, visible=False),  # live_embedding_info
        gr.update(value="*Analyzing embeddings...*"),  # embedding_method_info
        gr.update(visible=False)  # live_embedding_viz
    )

    try:
        # 2. Get the full response from the agent
        response = get_agent_response(message, history[:-1], current_user)
        
        history[-1][1] = response["text_answer"]
        
        # 4. Prepare embedding info
        embedding_display = {}
        embedding_method_text = ""
        embedding_viz_update = gr.update(visible=False)
        
        # <-- FIX for KeyError: Add check for embedding_info -->
        if "embedding_info" in response and response["embedding_info"] and "embedding_stats" in response["embedding_info"]:
            embedding_stats = response["embedding_info"]["embedding_stats"]
            embedding_display = {
                "Model": embedding_stats["model_name"],
                "Dimensions": embedding_stats["dimensions"],
                "Vector Norm": round(embedding_stats["vector_norm"], 4),
                "Mean": round(embedding_stats["vector_mean"], 4),
                "Std Dev": round(embedding_stats["vector_std"], 4),
                "Sample Vector": response["embedding_info"]["vector_sample"]
            }
            
            if response.get("semantic_search_used", False):
                embedding_method_text = f"🔍 **Semantic Search Used** - Retrieved {response.get('retrieved_docs_count', 0)} re-ranked documents (RAG-Fusion + CRAG)"
            elif "knowledge_graph_search" in response["thinking_markdown"]:
                 embedding_method_text = f"🕸️ **Knowledge Graph Used** - Retrieved structured relationships (Graph RAG)"
            elif "database_query_agent" in response["thinking_markdown"]:
                embedding_method_text = f"🗄️ **SQL Query Used** - Direct database query"
            else:
                 embedding_method_text = "❔ **Direct Answer** - Agent answered from instructions."

            if response.get("embedding_viz"):
                 embedding_viz_update = gr.update(value=response["embedding_viz"], visible=True)
        elif "error" in response.get("embedding_info", {}):
            embedding_method_text = "❌ Error analyzing query embedding."
        # <-- END FIX -->
        
        # 5. Final yield
        plot_update = gr.update(visible=False)
        if response["chart_figure"]:
            plot_update = gr.update(value=response["chart_figure"], visible=True)
        
        suggestions_list = response["suggested_questions"]
        dataframe_value = [[q] for q in suggestions_list]
        suggestions_box_update = gr.update(visible=True) if suggestions_list else gr.update(visible=False)
        
        yield (
            history, 
            plot_update, 
            response["thinking_markdown"],
            gr.Dataframe(value=dataframe_value), 
            suggestions_box_update,
            "",  # Clear textbox
            gr.update(),  # last_query
            json.dumps(suggestions_list),  # suggestions_store
            response.get("trace_id", ""), # trace_id
            gr.update(value=embedding_display, visible=True),  # live_embedding_info
            gr.update(value=embedding_method_text),  # embedding_method_info
            embedding_viz_update  # live_embedding_viz
        )
               
    except Exception as e:
        print(f"An error occurred in chat_ui_updater: {e}")
        traceback.print_exc()
        history[-1][1] = "Sorry, a critical error occurred. Please check the logs."
        
        yield (
            history, gr.update(), gr.update(value=f"Error: {e}"), gr.update(), 
            gr.update(visible=False), "", gr.update(), gr.update(), gr.State(""),
            gr.update(value={"Error": str(e)}, visible=True),
            gr.update(value="❌ Error during agent execution"),
            gr.update(visible=False)
        )

# --- 7. GRADIO UI LAYOUT WITH AUTHENTICATION ---

# Monkey patch for Gradio JSON schema bug
original_get_type = gradio_client.utils.get_type
def patched_get_type(schema: Any) -> Any:
    if isinstance(schema, bool):
        return "any"
    return original_get_type(schema)
gradio_client.utils.get_type = patched_get_type


with gr.Blocks(
    theme=gr.themes.Monochrome(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate"), 
    title="FHIR RAG Chatbot",
    css="""... (your existing css) ..."""
) as demo:
    
    # ... (All your existing Gradio layout code) ...
    # --- State Variables ---
    current_user = gr.State("")
    login_message = gr.Textbox(label="Status", visible=False, interactive=False)
    last_query = gr.Textbox(visible=False)
    suggestions_store = gr.Textbox(visible=False)
    selected_suggestion_index = gr.Number(label="Selected Index", visible=False)
    current_trace_id_store = gr.State("") # For feedback logging
    
    # --- Login Interface ---
    with gr.Group(visible=True) as login_form:
        gr.Markdown("# 🔐 Login Required")
        gr.Markdown("### Data Insights AI-Copilot (Bangladesh Data)")
        with gr.Row():
            with gr.Column(scale=1): gr.Markdown("")
            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("**Please log in to access the system:**")
                    username_input = gr.Textbox(label="Username", placeholder="Enter your username", max_lines=1, interactive=True, value="")
                    password_input = gr.Textbox(label="Password", placeholder="Enter your password", type="password", max_lines=1, interactive=True, value="")
                    with gr.Row():
                        login_btn = gr.Button("Login", variant="primary", scale=2)
                        clear_btn = gr.Button("Clear", variant="secondary", scale=1)
            with gr.Column(scale=1): gr.Markdown("")
    
    # --- Main Application Interface (Hidden by default) ---
    with gr.Group(visible=False) as main_interface:
        # Header
        with gr.Row():
            gr.Markdown("# Data Insights AI-Copilot (Bangaldesh Data)")
            with gr.Column(scale=1, min_width=200):
                user_display = gr.Markdown("", elem_classes=["user-info"])
                logout_btn = gr.Button("Logout", variant="secondary", size="sm")
        
        # Main Chat
        with gr.Row():
            with gr.Column(scale=1):
                # FIX: Add type='messages'
                chatbot = gr.Chatbot(label="Chat History", height=400, type="messages")
                textbox = gr.Textbox(placeholder="Ask a question...", container=False, scale=7, max_lines=3)
                submit_btn = gr.Button("Send", variant="primary")
            with gr.Column(scale=2):
                plot = gr.Plot(label="Chart Visualization", visible=False)
                with gr.Accordion("Show Agent's Reasoning", open=False):
                    thinking_box = gr.Markdown(label="Agent's Thoughts", value="*Waiting for a question...*")

        # Live Embedding Analysis
        with gr.Accordion("🧠 Query Embedding Analysis", open=False):
            gr.Markdown("### Automatic embedding analysis for every query")
            with gr.Row():
                with gr.Column(scale=1):
                    live_embedding_info = gr.JSON(label="Query Embedding Stats", value={}, visible=False)
                    embedding_method_info = gr.Markdown(value="*Ask a question to see embedding analysis*", label="Method Used")
                with gr.Column(scale=2):
                    live_embedding_viz = gr.Plot(label="Live Embedding Visualization", visible=False)

        # Embedding Explorer
        with gr.Accordion("🔬 Embedding Explorer", open=False):
            gr.Markdown("### Explore how embeddings work in your RAG system")
            with gr.Row():
                embedding_query = gr.Textbox(label="Test Query for Embedding Analysis", placeholder="Enter any query to see its embedding...", scale=3)
                analyze_btn = gr.Button("Analyze Embeddings", variant="secondary", scale=1)
            with gr.Row():
                with gr.Column(scale=1):
                    embedding_info = gr.JSON(label="Embedding Statistics", value={})
                with gr.Column(scale=2):
                    embedding_viz = gr.Plot(label="Embedding Visualization", visible=False)
            with gr.Accordion("Retrieved Documents (Post-Fusion, Post-Grading)", open=False):
                retrieved_docs = gr.Dataframe(
                    headers=["Rank", "Content", "Re-Ranker Score"],
                    label="Documents Retrieved by RAG", visible=False,
                    interactive=False, value=[]
                )
            embedding_status = gr.Textbox(label="Status", visible=False, interactive=False)

        # Suggestions and Feedback
        with gr.Group(visible=True) as suggestions_box:
            with gr.Row():
                suggestions_df = gr.Dataframe(
                    headers=["Suggested Questions"],
                    value=[["What is the total number of patients?"], 
                           ["Show the patient distribution by gender."], 
                           ["What are the top 5 most common conditions?"]],
                    col_count=(1, "fixed"), interactive=False, 
                    label="Suggestions (Select a row to ask)",
                )
            with gr.Row():
                gr.Markdown("Rate the quality of the last suggestion you clicked:")
                good_btn = gr.Button("Good 👍")
                bad_btn = gr.Button("Bad 👎")
            feedback_toast = gr.Textbox(label="Feedback Status", interactive=False, visible=False)

    
    # --- 8. GRADIO EVENT HANDLERS ---
    
    # ... (All your existing Gradio handler functions) ...
    def handle_login(username: str, password: str) -> Tuple[gr.update, gr.update, gr.update, str, str, str, gr.update]:
        is_valid, message = authenticate_user(username, password)
        if is_valid:
            return (gr.update(visible=False), gr.update(visible=True), gr.update(value=f"**Logged in as:** {username}", visible=True),
                    username, "", "", gr.update(value="Login successful!", visible=False))
        else:
            return (gr.update(visible=True), gr.update(visible=False), gr.update(value="", visible=False),
                    "", username, "", gr.update(value=message, visible=True))

    def handle_logout() -> Tuple[gr.update, gr.update, gr.update, str, str, str, gr.update]:
        return (gr.update(visible=True), gr.update(visible=False), gr.update(value="", visible=False),
                "", "", "", gr.update(value="Logged out successfully", visible=True))

    def submit_and_clear(message: str, history: List[List[str]], user: str) -> Generator[Tuple, None, None]:
        # Convert Gradio's `type="messages"` format to the list format our agent expects
        history_list_format = []
        for msg in history:
            if msg["role"] == "user":
                history_list_format.append([msg["content"], None])
            elif msg["role"] == "assistant" and history_list_format:
                history_list_format[-1][1] = msg["content"]
        
        for update in chat_ui_updater(message, history_list_format, user):
            # Convert back to Gradio's `type="messages"` format
            history_msg_format = []
            for user_msg, ai_msg in update[0]:
                history_msg_format.append({"role": "user", "content": user_msg})
                if ai_msg:
                    history_msg_format.append({"role": "assistant", "content": ai_msg})
            
            # Yield the updated tuple with the correct history format
            yield (history_msg_format,) + update[1:]

    chat_outputs = [
        chatbot, plot, thinking_box, suggestions_df, suggestions_box, 
        textbox, last_query, suggestions_store,
        current_trace_id_store,
        live_embedding_info, embedding_method_info, live_embedding_viz
    ]
    
    submit_btn.click(submit_and_clear, [textbox, chatbot, current_user], chat_outputs).then(lambda: "", None, textbox)
    textbox.submit(submit_and_clear, [textbox, chatbot, current_user], chat_outputs).then(lambda: "", None, textbox)

    def handle_suggestion_select(evt: gr.SelectData) -> Tuple[str, int]:
        if evt.value:
            selected_question = str(evt.value).strip()
            selected_index = evt.index[0]
            return selected_question, selected_index
        return "", 0
        
    suggestions_df.select(handle_suggestion_select, None, [textbox, selected_suggestion_index])
    
    good_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(1, visible=False), current_trace_id_store], [feedback_toast])
    bad_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(-1, visible=False), current_trace_id_store], [feedback_toast])

    def analyze_embeddings(query: str) -> Tuple[Dict, gr.update, gr.update, gr.update]:
        if not query.strip():
            return ({}, gr.update(visible=False), gr.update(value=[], visible=False), gr.update(value="Please enter a query to analyze", visible=True))
        try:
            results = enhanced_rag_search(query)
            if "error" in results:
                return ({"error": results["error"]}, gr.update(visible=False), gr.update(value=[], visible=False), gr.update(value=f"Error: {results['error']}", visible=True))
            embedding_info_display = {
                "Model": results["embedding_info"]["embedding_stats"]["model_name"],
                "Dimensions": results["embedding_info"]["embedding_stats"]["dimensions"],
                "Vector Norm": round(results["embedding_info"]["embedding_stats"]["vector_norm"], 4),
                "Mean Value": round(results["embedding_info"]["embedding_stats"]["vector_mean"], 4),
                "Std Deviation": round(results["embedding_info"]["embedding_stats"]["vector_std"], 4),
                "Sample Vector (first 10)": results["embedding_info"]["vector_sample"]
            }
            docs_df = [[doc["index"], doc["content"], round(doc["reranker_score"], 4)] for doc in results["retrieved_docs"]]
            viz = results["visualization"].get("visualization", None)
            viz_visible = viz is not None
            return (embedding_info_display, gr.update(value=viz, visible=viz_visible) if viz else gr.update(visible=False),
                    gr.update(value=docs_df, visible=len(docs_df) > 0),
                    gr.update(value=f"✅ Analysis complete! Found {results['total_docs_found']} re-ranked documents.", visible=True))
        except Exception as e:
            return ({"error": str(e)}, gr.update(visible=False), gr.update(value=[], visible=False), gr.update(value=f"Error during analysis: {str(e)}", visible=True))
    
    analyze_btn.click(
        analyze_embeddings,
        inputs=[embedding_query],
        outputs=[embedding_info, embedding_viz, retrieved_docs, embedding_status]
    )
    embedding_query.submit(
        analyze_embeddings,
        inputs=[embedding_query],
        outputs=[embedding_info, embedding_viz, retrieved_docs, embedding_status]
    )
    
    clear_btn.click(lambda: ("", ""), outputs=[username_input, password_input])

    login_outputs = [
        login_form, main_interface, user_display, current_user, 
        username_input, password_input, login_message
    ]
    
    login_btn.click(
        handle_login,
        inputs=[username_input, password_input],
        outputs=login_outputs
    )
    password_input.submit(
        handle_login,
        inputs=[username_input, password_input], 
        outputs=login_outputs
    )
    logout_btn.click(
        handle_logout,
        outputs=login_outputs
    )

# --- 9. LAUNCH APPLICATION ---

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        inbrowser=True,
        show_error=True,
        quiet=False
    )