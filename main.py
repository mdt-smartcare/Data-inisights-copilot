# --- Standard Library Imports ---
import os
import re
import json
import yaml
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
from langchain.chains import RetrievalQA  # Kept as per "don't remove"
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.embeddings import Embeddings

# --- LangChain Community/OpenAI Imports ---
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

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
rag_retriever = AdvancedRAGRetriever(config=rag_config)

# --- Main Agent Prompt Template ---
prompt_template = ChatPromptTemplate.from_messages([
    ("system", """You are a senior data analyst. Your goal is to provide clear answers with valuable context and proactive suggestions.
    **Core Instructions:**
    1.  **Answer the User's Question Directly:** Always provide the direct answer first.
    2.  **Add Context and Insight:** If the user asks for a count of a specific category (e.g., female patients), you must also provide the count of the contrasting category (e.g., male patients) and express the results as percentages of the total.
    3.  **Be Proactive with Visuals:** Based on your contextual analysis, proactively generate a `chart_json` object that visualizes the comparison (e.g., a pie chart for gender distribution), even if the user didn't explicitly ask for a chart.
    4.  **Suggest Next Steps:** Always provide three relevant follow-up questions in the `suggested_questions` key.
    **JSON Output Format:**
    Always provide a JSON block after your text answer with "chart_json" and "suggested_questions".
    ```json
    {{
      "chart_json": {{ "title": "...", "type": "pie", "data": {{ "labels": ["A", "B"], "values": [1, 2] }} }},
      "suggested_questions": ["Follow-up 1?", "Follow-up 2?", "Follow-up 3?"]
    }}
    ```"""),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# --- AGENT TOOLS ---
tools: List[Tool] = [
    Tool(
        name="database_query_agent", 
        func=sql_agent.invoke, 
        description="Use this to answer any question about the data in the database. This includes counting, listing, finding, or aggregating patient data, conditions, procedures, etc. This should be your default tool for any data-related query."
    ),
    Tool(
        name="semantic_patient_search", 
        func=rag_retriever.invoke,  # Use the new retriever's invoke method
        description="Use this ONLY when the user asks a question about a specific patient that requires searching through their unstructured notes or records for deeper context. Do NOT use for counting or listing general information."
    ),
]

# --- NEW: 2. INITIALIZE LANGFUSE HANDLER ---
# The handler automatically reads the environment variables you just set
langfuse_handler = CallbackHandler()

# --- Main Agent Executor ---
main_agent = create_tool_calling_agent(llm, tools, prompt_template)
main_agent_executor = AgentExecutor(
    agent=main_agent, 
    tools=tools, 
    verbose=True, 
    handle_parsing_errors=True, 
    return_intermediate_steps=True
)
print("--- FHIR RAG Chatbot is Ready ---")

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
    log = "### Agent Thinking Process\n\n"
    if not intermediate_steps: 
        return log + "No intermediate steps."
    
    for action, observation in intermediate_steps:
        log += f"**Thought:** {str(action.log)}\n\n**Tool:** `{action.tool}`\n\n"
        
        # Check if tool_input is a dict (like from sql_agent) or string
        if isinstance(action.tool_input, dict):
            input_str = action.tool_input.get("input", str(action.tool_input))
        else:
            input_str = str(action.tool_input)
            
        log += f"**Input:**\n```\n{input_str}\n```\n\n"
        log += f"**Output:**\n```\n{str(observation)}\n```\n---\n"
    return log

def log_feedback(query: str, suggestions_json: str, selected_index: int, rating: float) -> gr.update:
    """Logs user feedback on suggested questions to a CSV file."""
    try:
        if not query or not suggestions_json or selected_index is None:
            return gr.update(value="Could not log feedback: Missing context.", visible=True)
        
        suggestions_list = json.loads(suggestions_json)
        selected_question = suggestions_list[int(selected_index)]
        
        feedback_data = {
            "timestamp": [pd.Timestamp.now()], 
            "query": [query], 
            "suggested_question": [selected_question], 
            "rating": [rating]
        }
        df = pd.DataFrame(feedback_data)
        
        file_exists = os.path.isfile(Config.FEEDBACK_LOG_FILE)
        df.to_csv(Config.FEEDBACK_LOG_FILE, mode='a', header=not file_exists, index=False)
        
        return gr.update(value=f"Feedback logged (Rating: {rating})", visible=True)
        
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return gr.update(value="Error logging feedback.", visible=True)

# --- AUTHENTICATION FUNCTIONS ---
# NOTE: The following two functions (login_interface, logout_user) define
# logic that is re-implemented in the `handle_login` and `handle_logout`
# functions within the `gr.Blocks` context. They are not directly
# used by the final app's event handlers but are kept per request.

def authenticate_user(username: str, password: str) -> Tuple[bool, str]:
    """Authenticate user credentials against the config."""
    if not username or not password:
        return False, "Please enter both username and password"
    
    if username in Config.USERS and Config.USERS[username] == password:
        return True, f"Welcome, {username}!"
    else:
        return False, "Invalid username or password"

def login_interface(username: str, password: str) -> Tuple[gr.update, gr.update, gr.update, str]:
    """Handle login form submission (Not used by final app handlers)."""
    is_valid, message = authenticate_user(username, password)
    
    if is_valid:
        return (
            gr.update(visible=False),  # Hide login form
            gr.update(visible=True),   # Show main interface  
            gr.update(value=message, visible=True),  # Show welcome message
            username  # Store current user
        )
    else:
        return (
            gr.update(visible=True),   # Keep login form visible
            gr.update(visible=False),  # Keep main interface hidden
            gr.update(value=message, visible=True),  # Show error message
            ""  # Clear user
        )

def logout_user() -> Tuple[gr.update, gr.update, gr.update, str]:
    """Handle logout (Not used by final app handlers)."""
    return (
        gr.update(visible=True),   # Show login form
        gr.update(visible=False),  # Hide main interface
        gr.update(value="Logged out successfully", visible=True),  # Show logout message
        ""  # Clear current user
    )

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

def create_embedding_visualization(query: str, retrieved_docs: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Create visualizations for embedding analysis.
    - If docs are provided, shows a 2D PCA scatter plot of query vs. docs.
    - If no docs, shows a bar chart of the query's embedding vector.
    """
    try:
        # Get query embedding
        query_embedding = np.array(embedding_model.embed_query(query))
        
        if retrieved_docs and len(retrieved_docs) > 0:
            # --- PCA 2D Scatter Plot ---
            doc_texts = [doc.page_content[:200] for doc in retrieved_docs[:5]]  # Limit for visualization
            doc_embeddings = [embedding_model.embed_query(text) for text in doc_texts]
            
            all_embeddings = np.array([query_embedding] + doc_embeddings)
            
            pca = PCA(n_components=2)
            embeddings_2d = pca.fit_transform(all_embeddings)
            
            similarities = [cosine_similarity([query_embedding], [doc_emb])[0][0] 
                          for doc_emb in doc_embeddings]
            
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
                        colorbar=dict(title="Similarity"),
                        cmin=0, cmax=1
                    ),
                    name=f'Doc {i+1}',
                    text=[f"Doc {i+1}: {doc_text[:50]}...<br>Similarity: {similarity:.3f}"],
                    hovertemplate="<b>%{text}</b><extra></extra>"
                ))
            
            fig.update_layout(
                title="Embedding Space Visualization (PCA 2D)",
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
        
        # 2. Perform RAG search
        # Using _get_relevant_documents to bypass the full chain logic for analysis
        retrieved_docs = rag_retriever._get_relevant_documents(query)
        
        # 3. Create visualization
        viz_info = create_embedding_visualization(query, retrieved_docs)
        
        # 4. Format retrieved documents info
        docs_info = []
        similarities = viz_info.get("similarities", [])
        for i, doc in enumerate(retrieved_docs[:5]):  # Limit to 5 for display
            docs_info.append({
                "index": i + 1,
                "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                "metadata": doc.metadata,
                "similarity": similarities[i] if i < len(similarities) else 0
            })
        
        return {
            "query": query,
            "embedding_info": embedding_info,
            "retrieved_docs": docs_info,
            "visualization": viz_info,
            "total_docs_found": len(retrieved_docs)
        }
        
    except Exception as e:
        return {"error": f"Enhanced RAG search failed: {str(e)}"}

# --- 5. CORE AGENT AND UI LOGIC ---

def get_agent_response(message: str) -> Dict[str, Any]:
    """
    Runs the main agent executor and formats the output, including
    live embedding analysis for the query.
    """
    # --- NEW: 3. ADD THE LANGFUSE CALLBACK TO YOUR INVOCATION ---
    # This tells LangChain to send all trace data for this specific run to Langfuse
    result = main_agent_executor.invoke(
        {"input": message},
        {"callbacks": [langfuse_handler]} # <-- THIS IS THE ONLY CHANGE NEEDED HERE
    )
    full_response = result.get("output", "An error occurred.")
    
    # Always get embedding analysis for every query
    embedding_analysis = get_embedding_info(message)
    
    # Check if semantic search was used by examining intermediate steps
    semantic_search_used = False
    retrieved_docs = []
    for action, observation in result.get("intermediate_steps", []):
        if action.tool == "semantic_patient_search":
            semantic_search_used = True
            try:
                # Re-fetch docs for visualization (agent observation is just text)
                retrieved_docs = rag_retriever._get_relevant_documents(message)
            except Exception as e:
                print(f"Could not re-fetch docs for viz: {e}")
                retrieved_docs = []
            break
    
    # Create visualization for the query's embedding
    viz_info = create_embedding_visualization(message, retrieved_docs if semantic_search_used else None)
    
    # Standardize the output format
    parsed_output = {
        "text_answer": full_response, 
        "chart_figure": None,
        "suggested_questions": [], 
        "thinking_markdown": format_thinking_process(result.get("intermediate_steps", [])),
        "embedding_info": embedding_analysis,
        "embedding_viz": viz_info.get("visualization", None),
        "semantic_search_used": semantic_search_used,
        "retrieved_docs_count": len(retrieved_docs) if retrieved_docs else 0
    }
    
    # Try to parse the JSON block for charts and suggestions
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

def chat_ui_updater(message: str, history: List[List[str]]) -> Generator[Tuple, None, None]:
    """
    A generator function to handle the chat UI updates, including streaming.
    Yields tuples of gr.update objects for all outputs.
    """
    if not history:
        history = []
    
    # Add user message to history
    history.append([message, ""])
    
    # 1. First yield: Show user message and "thinking" status
    yield (
        history, 
        gr.update(visible=False),  # plot
        gr.update(value="*Agent is thinking...*"),  # thinking_box
        gr.Dataframe(value=[]),  # suggestions_df
        gr.update(visible=False),  # suggestions_box
        "",  # textbox
        gr.Textbox(value=message),  # last_query
        gr.Textbox(),  # suggestions_store
        gr.update(value={}, visible=False),  # live_embedding_info
        gr.update(value="*Analyzing embeddings...*"),  # embedding_method_info
        gr.update(visible=False)  # live_embedding_viz
    )

    try:
        # 2. Get the full response from the agent
        response = get_agent_response(message)
        
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
            if response.get("semantic_search_used", False):
                embedding_method_text = f"🔍 **Semantic Search Used** - Retrieved {response.get('retrieved_docs_count', 0)} documents using BGE-M3 embeddings"
                if response.get("embedding_viz"):
                    embedding_viz_update = gr.update(value=response["embedding_viz"], visible=True)
            else:
                embedding_method_text = f"🗄️ **SQL Query Used** - Direct database query (embeddings generated for analysis only)"
                if response.get("embedding_viz"):
                    embedding_viz_update = gr.update(value=response["embedding_viz"], visible=True)
        
        # 3. Stream the text response
        bot_message_so_far = ""
        for char in response["text_answer"]:
            bot_message_so_far += char
            history[-1][1] = bot_message_so_far  # Update last bot message
            
            # Yield streaming update
            yield (
                history, gr.update(), gr.update(), gr.update(), gr.update(),
                "", gr.update(), gr.update(),
                gr.update(), gr.update(), gr.update() # Keep embedding info static
            )

        # 4. Final yield: Update with chart, suggestions, and full analysis
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
            gr.update(value=embedding_display, visible=True),  # live_embedding_info
            gr.update(value=embedding_method_text),  # embedding_method_info
            embedding_viz_update  # live_embedding_viz
        )
               
    except Exception as e:
        print(f"An error occurred in chat_ui_updater: {e}")
        history[-1][1] = "Sorry, an error occurred. Please check the logs."
        
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
            gr.update(value={"Error": str(e)}, visible=True),
            gr.update(value="❌ Error during embedding analysis"),
            gr.update(visible=False)
        )

# --- 6. GRADIO UI LAYOUT WITH AUTHENTICATION ---

# Monkey patch for Gradio JSON schema bug in some versions
# This prevents crashes when rendering complex components like gr.JSON
original_get_type = gradio_client.utils.get_type
def patched_get_type(schema: Any) -> Any:
    if isinstance(schema, bool):
        return "any"
    return original_get_type(schema)
gradio_client.utils.get_type = patched_get_type


with gr.Blocks(
    theme=gr.themes.Monochrome(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate"), 
    title="FHIR RAG Chatbot",
    css="""
    .user-info { 
        text-align: right; 
        padding: 10px; 
        background-color: #f0f0f0; 
        border-radius: 5px; 
        margin: 5px 0; 
    }
    """
) as demo:
    
    # --- State Variables ---
    current_user = gr.State("")
    login_message = gr.Textbox(label="Status", visible=False, interactive=False)
    last_query = gr.Textbox(visible=False)
    suggestions_store = gr.Textbox(visible=False)
    selected_suggestion_index = gr.Number(label="Selected Index", visible=False)

    
    # --- Login Interface ---
    with gr.Group(visible=True) as login_form:
        gr.Markdown("# 🔐 Login Required")
        gr.Markdown("### Data Insights AI-Copilot (Bangladesh Data)")
        
        with gr.Row():
            with gr.Column(scale=1): gr.Markdown("")  # Spacer
            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("**Please log in to access the system:**")
                    username_input = gr.Textbox(label="Username", placeholder="Enter your username", max_lines=1, interactive=True, value="")
                    password_input = gr.Textbox(label="Password", placeholder="Enter your password", type="password", max_lines=1, interactive=True, value="")
                    
                    with gr.Row():
                        login_btn = gr.Button("Login", variant="primary", scale=2)
                        clear_btn = gr.Button("Clear", variant="secondary", scale=1)
                        
            with gr.Column(scale=1): gr.Markdown("")  # Spacer
    
    
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
                chatbot = gr.Chatbot(label="Chat History", height=400)
                textbox = gr.Textbox(placeholder="Ask a question...", container=False, scale=7, max_lines=3)
                submit_btn = gr.Button("Send", variant="primary")
            with gr.Column(scale=2):
                plot = gr.Plot(label="Chart Visualization", visible=False)
                with gr.Accordion("Show Agent's Reasoning", open=False):
                    thinking_box = gr.Markdown(label="Agent's Thoughts", value="*Waiting for a question...*")

        # Live Embedding Analysis (for chat queries)
        with gr.Accordion("🧠 Query Embedding Analysis", open=False):
            gr.Markdown("### Automatic embedding analysis for every query")
            with gr.Row():
                with gr.Column(scale=1):
                    live_embedding_info = gr.JSON(label="Query Embedding Stats", value={}, visible=False)
                    embedding_method_info = gr.Markdown(value="*Ask a question to see embedding analysis*", label="Method Used")
                with gr.Column(scale=2):
                    live_embedding_viz = gr.Plot(label="Live Embedding Visualization", visible=False)

        # Embedding Explorer (Manual tool)
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
            
            with gr.Accordion("Retrieved Documents", open=False):
                retrieved_docs = gr.Dataframe(
                    headers=["Rank", "Content", "Similarity"],
                    label="Documents Retrieved by RAG",
                    visible=False,
                    interactive=False
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
                    col_count=(1, "fixed"), 
                    interactive=False, 
                    label="Suggestions (Select a row to ask)",
                )
            with gr.Row():
                gr.Markdown("Rate the quality of the last suggestion you clicked:")
                good_btn = gr.Button("Good 👍")
                bad_btn = gr.Button("Bad 👎")
            feedback_toast = gr.Textbox(label="Feedback Status", interactive=False, visible=False)

    
    # --- 7. GRADIO EVENT HANDLERS ---

    # --- Authentication Handlers ---
    
    def handle_login(username: str, password: str) -> Tuple[gr.update, gr.update, gr.update, str, str, str, gr.update]:
        """Handles the login button click event."""
        is_valid, message = authenticate_user(username, password)
        if is_valid:
            return (
                gr.update(visible=False),  # Hide login form
                gr.update(visible=True),   # Show main interface
                gr.update(value=f"**Logged in as:** {username}", visible=True),  # Update user display
                username,  # Store current user in state
                "",  # Clear username field
                "",  # Clear password field
                gr.update(value="Login successful!", visible=False)  # Hide login message
            )
        else:
            return (
                gr.update(visible=True),   # Keep login form visible
                gr.update(visible=False),  # Keep main interface hidden
                gr.update(value="", visible=False),  # Clear user display
                "",  # Clear current user state
                username,  # Keep username in field
                "",  # Clear password field
                gr.update(value=message, visible=True)  # Show error message
            )

    def handle_logout() -> Tuple[gr.update, gr.update, gr.update, str, str, str, gr.update]:
        """Handles the logout button click event."""
        return (
            gr.update(visible=True),   # Show login form
            gr.update(visible=False),  # Hide main interface
            gr.update(value="", visible=False),  # Clear user display
            "",  # Clear current user state
            "",  # Clear username field
            "",  # Clear password field
            gr.update(value="Logged out successfully", visible=True)  # Show logout message
        )

    # --- Chat Handlers ---

    def submit_and_clear(message: str, history: List[List[str]]) -> Generator[Tuple, None, None]:
        """Wrapper for the chat updater generator."""
        for update in chat_ui_updater(message, history):
            yield update

    # Define outputs for the chat UI
    chat_outputs = [
        chatbot, plot, thinking_box, suggestions_df, suggestions_box, 
        textbox, last_query, suggestions_store,
        live_embedding_info, embedding_method_info, live_embedding_viz
    ]
    
    submit_btn.click(submit_and_clear, [textbox, chatbot], chat_outputs).then(lambda: "", None, textbox)
    textbox.submit(submit_and_clear, [textbox, chatbot], chat_outputs).then(lambda: "", None, textbox)

    # --- Suggestion & Feedback Handlers ---
    
    def handle_suggestion_select(evt: gr.SelectData) -> Tuple[str, int]:
        """
        Handles clicking on a suggested question.
        Populates the textbox and stores the index for feedback.
        """
        if evt.value:
            # evt.value is the text of the first cell in the selected row
            selected_question = str(evt.value).strip()
            selected_index = evt.index[0]  # Row index
            return selected_question, selected_index
        return "", 0
        
    suggestions_df.select(handle_suggestion_select, None, [textbox, selected_suggestion_index])
    
    # Bind feedback buttons
    good_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(1, visible=False)], [feedback_toast])
    bad_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(-1, visible=False)], [feedback_toast])

    # --- Embedding Explorer Handlers ---

    def analyze_embeddings(query: str) -> Tuple[Dict, gr.update, gr.update, gr.update]:
        """Handles the 'Analyze Embeddings' button click for the explorer."""
        if not query.strip():
            return (
                {},
                gr.update(visible=False),
                gr.update(value=[], visible=False),
                gr.update(value="Please enter a query to analyze", visible=True)
            )
        
        try:
            results = enhanced_rag_search(query)
            
            if "error" in results:
                return (
                    {"error": results["error"]},
                    gr.update(visible=False),
                    gr.update(value=[], visible=False),
                    gr.update(value=f"Error: {results['error']}", visible=True)
                )
            
            # Prepare JSON for display
            embedding_info_display = {
                "Model": results["embedding_info"]["embedding_stats"]["model_name"],
                "Dimensions": results["embedding_info"]["embedding_stats"]["dimensions"],
                "Vector Norm": round(results["embedding_info"]["embedding_stats"]["vector_norm"], 4),
                "Mean Value": round(results["embedding_info"]["embedding_stats"]["vector_mean"], 4),
                "Std Deviation": round(results["embedding_info"]["embedding_stats"]["vector_std"], 4),
                "Sample Vector (first 10)": results["embedding_info"]["vector_sample"]
            }
            
            # Prepare dataframe
            docs_df = [
                [doc["index"], doc["content"], round(doc["similarity"], 4) if doc["similarity"] else "N/A"]
                for doc in results["retrieved_docs"]
            ]
            
            viz = results["visualization"].get("visualization", None)
            viz_visible = viz is not None
            
            return (
                embedding_info_display,
                gr.update(value=viz, visible=viz_visible) if viz else gr.update(visible=False),
                gr.update(value=docs_df, visible=len(docs_df) > 0),
                gr.update(value=f"✅ Analysis complete! Found {results['total_docs_found']} relevant documents.", visible=True)
            )
            
        except Exception as e:
            return (
                {"error": str(e)},
                gr.update(visible=False),
                gr.update(value=[], visible=False),
                gr.update(value=f"Error during analysis: {str(e)}", visible=True)
            )
    
    # Bind embedding explorer events
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
    
    # --- Login/Logout Event Bindings ---
    
    # Clear login fields button
    clear_btn.click(lambda: ("", ""), outputs=[username_input, password_input])

    # Define outputs for login/logout handlers
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

# --- 8. LAUNCH APPLICATION ---

if __name__ == "__main__":
    demo.launch(
        share=False,  # Do not create a public link
        server_name="127.0.0.1",  # Run on localhost
        inbrowser=True,  # Open in browser automatically
        show_error=True,  # Show errors in the browser
        quiet=False  # Print Gradio logs to console
    )