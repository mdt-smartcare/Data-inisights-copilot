# --- Standard Library Imports ---
import os
import re
import json
import yaml
import uuid
from typing import List, Dict, Any, Tuple, Optional, Generator

# --- Third-Party Core Imports ---
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gradio as gr
import gradio_client.utils  # For monkey patch
from dotenv import load_dotenv

# --- ML/Embeddings Imports ---
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity

# --- LangChain Core Imports ---
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

# --- LangChain Community/OpenAI Imports ---
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

# --- Langfuse Imports ---
from langfuse.langchain import CallbackHandler

# --- Local/Project Imports ---
from backend.rag.retrieve import AdvancedRAGRetriever

# --- 1. CONFIGURATION ---

load_dotenv()

class Config:
    """Centralized configuration for the application."""
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    DB_USER: str = "admin"
    DB_PASSWORD: str = "admin"
    DB_NAME: str = "Spice_BD"
    DB_URI: str = f"postgresql://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"
    EMBEDDING_MODEL_PATH: str = "./models/bge-m3"
    LLM_MODEL: str = "gpt-4o"
    FEEDBACK_LOG_FILE: str = "feedback_log.csv"
    
    # Authentication configuration
    USERS: Dict[str, str] = {
        "admin": "admin",
        "analyst": "analyst2024",
        "viewer": "view123"
    }

if not Config.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found or is empty in your .env file.")
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

# --- 2. AGENT AND TOOL SETUP ---

class LocalHuggingFaceEmbeddings(Embeddings):
    """Custom wrapper for SentenceTransformer to comply with LangChain Embeddings interface."""
    def __init__(self, model_id: str):
        self.model = SentenceTransformer(model_id)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents."""
        return self.model.encode(texts, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        return self.model.encode(text).tolist()

print("Initializing agent components...")
llm = ChatOpenAI(temperature=0, model_name=Config.LLM_MODEL)
embedding_model = LocalHuggingFaceEmbeddings(model_id=Config.EMBEDDING_MODEL_PATH)
db = SQLDatabase.from_uri(Config.DB_URI)

# --- SQL AGENT (The "Counter") ---
# This agent is responsible for querying structured data from the SQL database.
sql_agent = create_sql_agent(llm=llm, db=db, agent_type="openai-tools", verbose=True)

# --- RAG RETRIEVER (The "Finder") ---
# Load the RAG config file to find the correct vector store path
with open("config/embedding_config.yaml", 'r') as f:
    rag_config = yaml.safe_load(f)

# Initialize the advanced retriever for semantic search on unstructured notes
# Initialize the advanced retriever for semantic search on unstructured notes
rag_retriever = AdvancedRAGRetriever(config=rag_config)

# --- Main Agent Prompt Template (NCD SPECIALIZED) ---
system_prompt = """You are an advanced **NCD Clinical Data Intelligence Agent** specializing in Chronic Disease Management (Hypertension & Diabetes).
You have access to a comprehensive patient database (Spice_BD) containing structured vitals, demographics, and unstructured clinical notes.

**YOUR DECISION MATRIX:**

1.  **Use `sql_query_tool` (Structured Data) when:**
    * The user asks for **statistics**: Counts, averages, sums, or percentages.
    * The user asks about **specific biomarkers**: `systolic`/`diastolic` BP, `glucose_value`, `hba1c`, `bmi`.
    * The user filters by demographics: Age groups, gender, location.

2.  **Use `rag_patient_context_tool` (Unstructured Data) when:**
    * The user asks about **qualitative factors**: Symptoms ("dizziness", "blurred vision"), lifestyle ("smoker", "diet"), or adherence ("non-compliant", "refused meds").
    * You need to find specific patient narratives, doctor's notes, or care plans.

3.  **Use BOTH tools (Hybrid) when:**
    * The user asks a complex question: "Find patients with 'poor adherence' notes [RAG] and calculate their average HbA1c [SQL]."

4.  **Suggest Next Steps:** Always provide three relevant follow-up questions in the `suggested_questions` key.

**NCD CLINICAL REASONING INSTRUCTIONS:**

* **Synonym & Concept Expansion:**
    * **Hypertension (HTN):** Map "High BP", "Pressure", or "Tension" to `systolic` > 140 or `diastolic` > 90. Look for "Stage 1", "Stage 2", or "Hypertensive Crisis".
    * **Diabetes (DM):** Map "Sugar", "Glucose", "Sweet" to `glucose_value` (FBS/RBS) or `hba1c`. Distinguish between "Type 1" (T1DM) and "Type 2" (T2DM).
    * **Comorbidities:** Actively look for patients with *both* HTN and DM, as they are high-risk.

* **Contextualization (The "So What?"):**
    * **Interpret Vitals:** Don't just say "Avg BP is 150/95". Say "Avg BP is 150/95, which indicates **uncontrolled Stage 2 Hypertension** in this cohort."
    * **Interpret Glucose:** Don't just say "Avg Glucose is 12 mmol/L". Say "Avg Glucose is 12 mmol/L, indicating **poor glycemic control**."
    * **Risk Stratification:** Highlight if a finding implies high cardiovascular risk (e.g., high BP + smoker).

**RESPONSE FORMAT INSTRUCTIONS:**
1.  **Direct Answer:** Start with the numbers or the finding.
2.  **Clinical Interpretation:** Explain the NCD significance (Control status, Risk level).
3.  **Visuals:** You MUST generate a JSON for a chart if comparing groups (e.g., "Controlled vs Uncontrolled").

**JSON OUTPUT FORMAT:**
Always append this JSON block at the end of your response:
```json
{{
    "chart_json": {{ "title": "...", "type": "pie", "data": {{ "labels": ["A", "B"], "values": [1, 2] }} }},
    "suggested_questions": ["Follow-up 1?", "Follow-up 2?", "Follow-up 3?"]
}}
```
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# --- AGENT TOOLS (Refined Descriptions) ---
tools: List[Tool] = [
    Tool(
        name="sql_query_tool", 
        func=sql_agent.invoke, 
        description="""**PRIMARY TOOL FOR STATISTICS.** Use this to access the structured SQL database.
- Tables: patient_tracker (demographics, bp, glucose), patient_diagnosis (conditions), prescription.
- Capabilities: COUNT, AVG, GROUP BY, filtering by age/gender/date.
- Use for: "How many patients...", "Average glucose...", "Distribution of..."."""
    ),
    Tool(
        name="rag_patient_context_tool", 
        func=rag_retriever.invoke, 
        description="""**PRIMARY TOOL FOR CLINICAL CONTEXT.**
Use this to search unstructured text, medical notes, and semantic descriptions.
- Capabilities: Semantic search for symptoms, lifestyle, risk factors, and specific diagnoses.
- Use for: "Find patients who complain of...", "Show me records regarding...", "Details about patient X..."."""
    ),
]

# --- Main Agent Executor ---
main_agent = create_tool_calling_agent(llm, tools, prompt_template)
main_agent_executor = AgentExecutor(
    agent=main_agent, 
    tools=tools, 
    verbose=True, 
    handle_parsing_errors=True, 
    return_intermediate_steps=True
)

# --- 3. HELPER AND LOGGING FUNCTIONS ---

def create_plotly_chart(chart_json: Dict[str, Any]) -> Optional[go.Figure]:
    """Creates a Plotly figure from a JSON-like dictionary."""
    try:
        title = chart_json.get("title", "Chart")
        chart_type = chart_json.get("type", "bar")
        data = chart_json.get("data", {})
        labels, values = data.get("labels", []), data.get("values", [])
        
        if not labels or not values: 
            return None
        
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
    """Formats the agent's intermediate steps into a readable markdown string."""
    log = "###  Clinical Reasoning Process\n\n"
    if not intermediate_steps: 
        return log + "Direct response generated."
    
    for action, observation in intermediate_steps:
        log += f"**Step:** Executing `{action.tool}`\n"
        
        # Check if tool_input is a dict (like from sql_agent) or string
        if isinstance(action.tool_input, dict):
            input_str = action.tool_input.get("input", str(action.tool_input))
        else:
            input_str = str(action.tool_input)
            
        log += f"**Query:** `{input_str}`\n"
        log += f"**Finding:** {str(observation)[:200]}...\n\n"
    return log

def log_feedback(query: str, suggestions_json: str, selected_index: int, rating: float, trace_id: str) -> gr.update:
    """Logs user feedback on suggested questions to a CSV file."""
    try:
        if not query or not suggestions_json or selected_index is None:
            return gr.update(value="Could not log feedback: Missing context.", visible=True)
        
        suggestions_list = json.loads(suggestions_json)
        # Safe access to list index
        if 0 <= int(selected_index) < len(suggestions_list):
            selected_question = suggestions_list[int(selected_index)]
        else:
            selected_question = ""
        
        feedback_data = {
            "timestamp": [pd.Timestamp.now()], 
            "query": [query], 
            "suggested_question": [selected_question], 
            "rating": [rating],
            "trace_id": [trace_id]
        }
        df = pd.DataFrame(feedback_data)
        
        file_exists = os.path.isfile(Config.FEEDBACK_LOG_FILE)
        df.to_csv(Config.FEEDBACK_LOG_FILE, mode='a', header=not file_exists, index=False)
        
        return gr.update(value=f"Feedback logged (Rating: {rating})", visible=True)
        
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return gr.update(value="Error logging feedback.", visible=True)

# --- AUTHENTICATION FUNCTIONS ---

def authenticate_user(username: str, password: str) -> Tuple[bool, str]:
    """Authenticate user credentials against the config."""
    if not username or not password:
        return False, "Please enter both username and password"
    
    if username in Config.USERS and Config.USERS[username] == password:
        return True, f"Welcome, {username}!"
    else:
        return False, "Invalid username or password"

# --- 4. NEW EMBEDDING VISUALIZATION FUNCTIONS ---

def get_embedding_info(query: str) -> Dict[str, Any]:
    """Get detailed embedding information and statistics for a query."""
    try:
        # Generate embedding for the query
        query_embedding = embedding_model.embed_query(query)
        
        # Get embedding statistics
        embedding_stats = {
            "model_name": "BAAI/bge-m3",
            "dimensions": len(query_embedding),
            "vector_norm": float(np.linalg.norm(query_embedding)),
            "vector_mean": float(np.mean(query_embedding)),
            "vector_std": float(np.std(query_embedding)),
            "vector_min": float(np.min(query_embedding)),
            "vector_max": float(np.max(query_embedding))
        }
        
        # Sample of the embedding vector (first 10 dimensions)
        vector_sample = [round(float(x), 3) for x in query_embedding[:10]]
        
        return {
            "query": query,
            "embedding_stats": embedding_stats,
            "vector_sample": vector_sample,
            "full_vector": query_embedding
        }
    except Exception as e:
        return {"error": f"Failed to generate embedding: {str(e)}"}

def create_embedding_visualization(query: str, retrieved_docs_with_scores: Optional[List[Tuple[Document, float]]] = None) -> Dict[str, Any]:
    """
    Create visualizations for embedding analysis.
    - If docs are provided, shows a 2D PCA scatter plot of query vs. docs.
    - If no docs, shows a bar chart of the query's embedding vector.
    """
    try:
        # Get query embedding
        query_embedding = np.array(embedding_model.embed_query(query))
        
        if retrieved_docs_with_scores and len(retrieved_docs_with_scores) > 0:
            # --- PCA 2D Scatter Plot ---
            
            # Unpack the documents and scores
            retrieved_docs = [doc for doc, score in retrieved_docs_with_scores]
            reranker_scores = [score for doc, score in retrieved_docs_with_scores]
            
            doc_texts = [doc.page_content[:200] for doc in retrieved_docs[:5]] # Limit for visualization
            doc_embeddings = [embedding_model.embed_query(text) for text in doc_texts]
            
            all_embeddings = np.array([query_embedding] + doc_embeddings)
            
            pca = PCA(n_components=2)
            embeddings_2d = pca.fit_transform(all_embeddings)
            
            # Use the reranker scores
            similarities = reranker_scores[:5] # Make sure we only use scores for the docs we're plotting
            
            fig = go.Figure()
            
            # Add query point
            fig.add_trace(go.Scatter(
                x=[embeddings_2d[0][0]], 
                y=[embeddings_2d[0][1]],
                mode='markers',
                marker=dict(size=15, color='red', symbol='star'),
                name='Query',
                text=[f"Query: {query[:50]}..."],
                hovertemplate="<b>%{text}</b><extra></extra>"
            ))
            
            # Add document points
            for i, (doc_text, similarity) in enumerate(zip(doc_texts, similarities)):
                fig.add_trace(go.Scatter(
                    x=[embeddings_2d[i+1][0]], 
                    y=[embeddings_2d[i+1][1]],
                    mode='markers',
                    marker=dict(
                        size=12, 
                        color=similarity,
                        colorscale='Viridis',
                        colorbar=dict(title="Re-Rank Score"), # <-- CHANGED TITLE
                    ),
                    name=f'Doc {i+1}',
                    text=[f"Doc {i+1}: {doc_text[:50]}...<br>Re-Rank Score: {similarity:.3f}"], # <-- CHANGED TEXT
                    hovertemplate="<b>%{text}</b><extra></extra>"
                ))
            
            fig.update_layout(
                title="Semantic Space (Re-ranked)",
                xaxis_title="PCA Component 1",
                yaxis_title="PCA Component 2",
                showlegend=True,
                height=400
            )
            
            return {
                "visualization": fig,
                "similarities": similarities,
                "doc_texts": doc_texts
            }
        else:
            # --- Query Vector Bar Chart ---
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=list(range(min(50, len(query_embedding)))),
                y=query_embedding[:50],  # Show first 50 dimensions
                name="Embedding Values"
            ))
            fig.update_layout(
                title=f"Query Embedding Vector (First 50 dimensions)",
                xaxis_title="Dimension",
                yaxis_title="Value",
                height=300
            )
            
            return {"visualization": fig}
            
    except Exception as e:
        return {"error": f"Failed to create visualization: {str(e)}"}

def enhanced_rag_search(query: str) -> Dict[str, Any]:
    """
    Performs a RAG search and bundles it with embedding info and visualizations.
    Used by the 'Embedding Explorer' tab.
    """
    try:
        # 1. Get embedding info for the query
        embedding_info = get_embedding_info(query)
        if "error" in embedding_info:
            return embedding_info
        
        # 2. Perform RAG search *and get scores* using re-ranker
        # Assumes rag_retriever has the new `retrieve_and_rerank_with_scores` method
        # If not, this block needs to handle the fallback or ensure retrieve.py is updated.
        if hasattr(rag_retriever, 'retrieve_and_rerank_with_scores'):
             retrieved_docs_with_scores = rag_retriever.retrieve_and_rerank_with_scores(query)
        else:
             # Fallback if retrieve.py isn't updated yet (e.g. just returns docs)
             # This prevents main.py from crashing if retrieve.py is old
             docs = rag_retriever._get_relevant_documents(query)
             # Fake score 1.0 if no reranker logic present
             retrieved_docs_with_scores = [(doc, 1.0) for doc in docs]
        
        # 3. Create visualization
        viz_info = create_embedding_visualization(query, retrieved_docs_with_scores)
        
        # 4. Format retrieved documents info
        docs_info = []
        for i, (doc, score) in enumerate(retrieved_docs_with_scores[:5]): # Limit to 5 for display
            docs_info.append({
                "index": i + 1,
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "metadata": doc.metadata,
                "reranker_score": round(score, 4)
            })
        
        return {
            "query": query,
            "embedding_info": embedding_info,
            "retrieved_docs": docs_info,
            "visualization": viz_info,
            "total_docs_found": len(retrieved_docs_with_scores)
        }
        
    except Exception as e:
        return {"error": f"Enhanced RAG search failed: {str(e)}"}

# --- 5. CORE AGENT AND UI LOGIC ---

def get_agent_response(message: str) -> Dict[str, Any]:
    """
    Runs the main agent executor and formats the output, including
    live embedding analysis for the query.
    """
    # --- 1. Generate Trace ID Manually ---
    trace_id = str(uuid.uuid4())
    
    # --- 2. Create Handler without parameters (Langfuse will auto-generate trace) ---
    try:
        local_langfuse_handler = CallbackHandler()
    except Exception as e:
        print(f"Warning: Could not initialize Langfuse handler: {e}")
        local_langfuse_handler = None
    
    # --- 3. Invoke Agent with Handler ---
    callbacks = [local_langfuse_handler] if local_langfuse_handler else []
    result = main_agent_executor.invoke(
        {"input": message},
        {"callbacks": callbacks} if callbacks else {}
    )
    
    full_response = result.get("output", "An error occurred.")
    
    # Always get embedding analysis for every query
    embedding_analysis = get_embedding_info(message)
    
    # Check if RAG search was used by examining intermediate steps
    rag_search_used = False
    retrieved_docs_with_scores = []
    
    # Check tool usage in intermediate steps
    if result.get("intermediate_steps"):
        for action, observation in result.get("intermediate_steps"):
            if action.tool == "rag_patient_context_tool":
                rag_search_used = True
                try:
                    # Re-fetch docs for visualization (agent observation is just text)
                    # We re-run retrieval here solely for the visualization widget
                    if hasattr(rag_retriever, 'retrieve_and_rerank_with_scores'):
                        retrieved_docs_with_scores = rag_retriever.retrieve_and_rerank_with_scores(message)
                    else:
                        docs = rag_retriever._get_relevant_documents(message)
                        retrieved_docs_with_scores = [(d, 1.0) for d in docs]
                except Exception as e:
                    print(f"Could not re-fetch docs for viz: {e}")
                    retrieved_docs_with_scores = []
                break
    
    # Create visualization for the query's embedding
    viz_info = create_embedding_visualization(message, retrieved_docs_with_scores if rag_search_used else None)
    
    # Standardize the output format
    parsed_output = {
        "text_answer": full_response, 
        "chart_figure": None,
        "suggested_questions": [], 
        "thinking_markdown": format_thinking_process(result.get("intermediate_steps", [])),
        "embedding_info": embedding_analysis,
        "embedding_viz": viz_info.get("visualization", None),
        "rag_search_used": rag_search_used,
        "retrieved_docs_count": len(retrieved_docs_with_scores),
        "trace_id": trace_id # Pass the manual trace_id
    }
    
    # Try to parse the JSON block for charts and suggestions
    json_match = re.search(r'```json\s*({.*?})\s*```', full_response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            parsed_output["text_answer"] = full_response[:json_match.start()].strip()
            
            if chart_json := data.get("chart_json"):
                parsed_output["chart_figure"] = create_plotly_chart(chart_json)
            if questions := data.get("suggested_questions"):
                parsed_output["suggested_questions"] = questions
                
        except json.JSONDecodeError:
            print("Warning: Failed to parse JSON from agent response.")
            parsed_output["text_answer"] += " (Note: Visualization data was malformed)"
            
    return parsed_output

def chat_ui_updater(message: str, history: List[List[str]]) -> Generator[Tuple, None, None]:
    """
    A generator function to handle the chat UI updates with progress shown directly in chat.
    Yields tuples of gr.update objects for all outputs.
    """
    if not history:
        history = []
    
    # Add user message to history with empty bot response
    history.append([message, ""])
    
    try:
        # 1. Show "Query received" status
        history[-1][1] = "🔍 **Query received** - Analyzing your question..."
        yield (
            history, 
            gr.update(visible=False),  # plot
            gr.update(value="*Analyzing Clinical Data...*"),  # thinking_box
            gr.Dataframe(value=[]),  # suggestions_df
            gr.update(visible=False),  # suggestions_box
            "",  # textbox
            gr.Textbox(value=message),  # last_query
            gr.Textbox(value="[]"),  # suggestions_store
            gr.State(""), # current_trace_id_store
            gr.update(value={}, visible=False),  # live_embedding_info
            gr.update(value="*Selecting Query Strategy...*"),  # embedding_method_info
            gr.update(visible=False)  # live_embedding_viz
        )

        # 2. Show "Thinking" status
        history[-1][1] = " **Thinking...** "
        yield (
            history, gr.update(), gr.update(), gr.update(), gr.update(),
            "", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        )
        
        # 3. Get the full response from the agent (this is where the actual work happens)
        response = get_agent_response(message)
        
        # 4. Show "Processing results" status
        history[-1][1] = " **Processing results...** "
        yield (
            history, gr.update(), gr.update(), gr.update(), gr.update(),
            "", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        )
        
        # Prepare embedding information for live display
        embedding_display = {}
        embedding_method_text = ""
        embedding_viz_update = gr.update(visible=False)
        
        if "embedding_info" in response and "error" not in response["embedding_info"]:
            embedding_stats = response["embedding_info"]["embedding_stats"]
            embedding_display = {
                "Model": embedding_stats["model_name"],
                "Dimensions": embedding_stats["dimensions"],
                "Vector Norm": round(embedding_stats["vector_norm"], 4),
                "Mean": round(embedding_stats["vector_mean"], 4),
                "Std Dev": round(embedding_stats["vector_std"], 4),
                "Sample Vector": response["embedding_info"]["vector_sample"]
            }
            
            # Determine which method was used
            if response.get("rag_search_used", False):
                embedding_method_text = f" **Hybrid Search Used** - Retrieved {response.get('retrieved_docs_count', 0)} re-ranked documents using BGE-M3 + Reranker"
                # Show query complete status
                history[-1][1] = f" **Query Complete** - Found {response.get('retrieved_docs_count', 0)} relevant documents. Generating response..."
                if response.get("embedding_viz"):
                    embedding_viz_update = gr.update(value=response["embedding_viz"], visible=True)
            else:
                embedding_method_text = f" **Structured Query Used** - Direct SQL database query"
                history[-1][1] = " **Query Complete** - Retrieved structured data. Generating response..."
                if response.get("embedding_viz"):
                    embedding_viz_update = gr.update(value=response["embedding_viz"], visible=True)
        
        # Yield query complete status
        yield (
            history, gr.update(), gr.update(), gr.update(), gr.update(),
            "", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        )
        
        # 5. Stream the text response
        bot_message_so_far = ""
        for char in response["text_answer"]:
            bot_message_so_far += char
            history[-1][1] = bot_message_so_far  # Update last bot message
            
            # Yield streaming update
            yield (
                history, gr.update(), gr.update(), gr.update(), gr.update(),
                "", gr.update(), gr.update(),
                gr.update(), # Keep trace_id static
                gr.update(), gr.update(), gr.update()
            )

        # 6. Final yield: Complete with all visualizations
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
            gr.update(),  # last_query (already set)
            json.dumps(suggestions_list),  # suggestions_store
            response.get("trace_id", ""), # Pass trace_id to state
            gr.update(value=embedding_display, visible=True),  # live_embedding_info
            gr.update(value=embedding_method_text),  # embedding_method_info
            embedding_viz_update  # live_embedding_viz
        )
               
    except Exception as e:
        print(f"An error occurred in chat_ui_updater: {e}")
        history[-1][1] = f" **Error occurred:** {str(e)}\n\nPlease try again or rephrase your question."
        
        # Yield error state
        yield (
            history, 
            gr.update(), 
            gr.update(value=f"Error: {e}"),
            gr.update(), 
            gr.update(visible=False),
            "", 
            gr.update(), 
            gr.update(),
            gr.State(""), 
            gr.update(value={"Error": str(e)}, visible=True),
            gr.update(value=" Error during embedding analysis"),
            gr.update(visible=False)
        )

# --- 6. GRADIO UI ---
# Monkey patch for JSON bug
original_get_type = gradio_client.utils.get_type
gradio_client.utils.get_type = lambda s: "any" if isinstance(s, bool) else original_get_type(s)
theme = gr.themes.Citrus()
with gr.Blocks(theme=theme, title="Data Insights AI-Copilot") as demo:
    
    # State
    current_user = gr.State("")
    login_message = gr.Textbox(label="Status", visible=False, interactive=False)
    last_query = gr.Textbox(visible=False)
    suggestions_store = gr.Textbox(visible=False)
    selected_idx = gr.Number(label="Selected Index", visible=False)
    trace_id_store = gr.State("") # Store trace_id here

    # --- Login Interface ---
    with gr.Group(visible=True) as login_form:
        gr.Markdown("#  Clinical Login")
        with gr.Row():
            with gr.Column(scale=2):
                user_input = gr.Textbox(label="Username")
                pass_input = gr.Textbox(label="Password", type="password")
                login_btn = gr.Button("Login", variant="primary")

    # --- Main Interface ---
    with gr.Group(visible=False) as main_interface:
        with gr.Row():
            gr.Markdown("# Data Insights AI-Copilot (Bangladesh Data)")
            logout_btn = gr.Button("Logout", size="sm")
        
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(height=500, label="Analyst Chat", avatar_images=(None, "https://cdn-icons-png.flaticon.com/512/387/387569.png"))
                msg_box = gr.Textbox(placeholder="Ask a clinical question (e.g., 'Patients with hypertension over 50?')...", container=False)
                with gr.Row():
                    submit = gr.Button("Analyze", variant="primary")
                    clear = gr.Button("Clear")
            
            with gr.Column(scale=1):
                plot = gr.Plot(label="Population Health Insights", visible=False)
                with gr.Accordion(" Agent Reasoning", open=False):
                    reasoning = gr.Markdown("*Waiting for query...*")
                with gr.Accordion(" Embedding Analysis", open=False):
                    emb_info = gr.JSON(label="Vector Stats")
                    method_lbl = gr.Markdown()
                    emb_plot = gr.Plot()

        # Suggestions & Feedback
        with gr.Group(visible=True) as suggestions_box:
            with gr.Row():
                sugg_df = gr.Dataframe(headers=["Follow-up Questions"], interactive=False, col_count=(1, "fixed"), label="Suggestions")
            with gr.Row():
                gr.Markdown("Feedback:")
                btn_good = gr.Button(" Accurate")
                btn_bad = gr.Button(" Inaccurate")
            toast = gr.Textbox(visible=False, label="Log Status")
        
        # Embedding Explorer Tab
        with gr.Accordion("🛠️ Manual Explorer", open=False):
            with gr.Row():
                exp_query = gr.Textbox(label="Test Query")
                exp_btn = gr.Button("Explore")
            with gr.Row():
                exp_json = gr.JSON(label="Stats")
                exp_viz = gr.Plot()
            exp_docs = gr.Dataframe(headers=["Rank", "Content", "Re-Ranker Score"], label="Results")
            exp_status = gr.Textbox(label="Status")

    # --- HANDLERS ---
    
    def on_login(u, p):
        success, msg = authenticate_user(u, p)
        if success:
            return gr.update(visible=False), gr.update(visible=True), u
        return gr.update(visible=True), gr.update(visible=False), ""

    def on_logout():
        return gr.update(visible=True), gr.update(visible=False), ""

    def on_analyze(q):
        res = enhanced_rag_search(q)
        if "error" in res: 
            return {}, None, [], f"Error: {res['error']}"
        
        # Prepare table data correctly
        table_data = []
        for doc_info in res["retrieved_docs"]:
            table_data.append([doc_info["index"], doc_info["content"], doc_info["reranker_score"]])
            
        return res["embedding_info"], res["visualization"]["visualization"], table_data, f"Found {res['total_docs_found']} docs"

    # Wiring
    login_btn.click(on_login, [user_input, pass_input], [login_form, main_interface, current_user])
    pass_input.submit(on_login, [user_input, pass_input], [login_form, main_interface, current_user])
    logout_btn.click(on_logout, None, [login_form, main_interface, current_user])

    # Main Chat Wiring - progress now shown directly in chatbot
    chat_outs = [chatbot, plot, reasoning, sugg_df, suggestions_box, msg_box, last_query, suggestions_store, trace_id_store, emb_info, method_lbl, emb_plot]
    submit.click(chat_ui_updater, [msg_box, chatbot], chat_outs)
    msg_box.submit(chat_ui_updater, [msg_box, chatbot], chat_outs)

    # Suggestions & Feedback Wiring
    def on_select_suggestion(evt: gr.SelectData):
        return evt.value, evt.index[0]

    sugg_df.select(on_select_suggestion, None, [msg_box, selected_idx])
    btn_good.click(log_feedback, [last_query, suggestions_store, selected_idx, gr.Number(1, visible=False), trace_id_store], toast)
    btn_bad.click(log_feedback, [last_query, suggestions_store, selected_idx, gr.Number(-1, visible=False), trace_id_store], toast)
    
    # Explorer Wiring
    exp_btn.click(on_analyze, exp_query, [exp_json, exp_viz, exp_docs, exp_status])
    exp_query.submit(on_analyze, exp_query, [exp_json, exp_viz, exp_docs, exp_status])

if __name__ == "__main__":
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        inbrowser=False,
        show_error=True,
        quiet=False
    )