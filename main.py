import os
import re
import json
from typing import List, Dict, Any
import pandas as pd

# --- Core Dependencies ---
from dotenv import load_dotenv
import gradio as gr
from sentence_transformers import SentenceTransformer
import plotly.express as px

# --- LangChain Imports ---
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain_community.utilities import SQLDatabase
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent, Tool

# --- 1. CONFIGURATION ---

load_dotenv()

class Config:
    """ Centralized configuration for the application. """
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    DB_USER = "admin"
    DB_PASSWORD = "admin"
    DB_NAME = "views"
    DB_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"
    EMBEDDING_MODEL_PATH = "./models/bge-m3"
    VECTOR_DB_PATH = 'chroma_db_index_b-m3_full'
    LLM_MODEL = "gpt-4o"
    FEEDBACK_LOG_FILE = "feedback_log.csv"
    
    # Authentication configuration
    USERS = {
        "admin": "admin",
        "analyst": "analyst2024",
        "viewer": "view123"
    }

if not Config.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found or is empty in your .env file.")
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY

# --- 2. AGENT AND TOOL SETUP ---

class LocalHuggingFaceEmbeddings(Embeddings):
    def __init__(self, model_id): self.model = SentenceTransformer(model_id)
    def embed_documents(self, texts: List[str]) -> List[List[float]]: return self.model.encode(texts, show_progress_bar=False).tolist()
    def embed_query(self, text: str) -> List[float]: return self.model.encode(text).tolist()

print("Initializing agent components...")
llm = ChatOpenAI(temperature=0, model_name=Config.LLM_MODEL)
embedding_model = LocalHuggingFaceEmbeddings(model_id=Config.EMBEDDING_MODEL_PATH)
db = SQLDatabase.from_uri(Config.DB_URI)
sql_agent = create_sql_agent(llm=llm, db=db, agent_type="openai-tools", verbose=True)
vector_db = Chroma(persist_directory=Config.VECTOR_DB_PATH, embedding_function=embedding_model)
rag_retriever = vector_db.as_retriever(search_kwargs={"k": 3})
rag_chain = RetrievalQA.from_chain_type(llm=llm, retriever=rag_retriever)

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

tools = [
    Tool(name="database_query_agent", func=sql_agent.invoke, description="Use this to answer any question about the data in the database. This includes counting, listing, finding, or aggregating patient data, conditions, procedures, etc. This should be your default tool for any data-related query."),
    Tool(name="semantic_patient_search", func=rag_chain.invoke, description="Use this ONLY when the user asks a question about a specific patient that requires searching through their unstructured notes or records for deeper context. Do NOT use for counting or listing general information."),
]

main_agent = create_openai_tools_agent(llm, tools, prompt_template)
main_agent_executor = AgentExecutor(agent=main_agent, tools=tools, verbose=True, handle_parsing_errors=True, return_intermediate_steps=True)
print("--- FHIR RAG Chatbot is Ready ---")

# --- 3. HELPER AND LOGGING FUNCTIONS ---

def create_plotly_chart(chart_json: Dict[str, Any]) -> object:
    title = chart_json.get("title", "Chart")
    chart_type = chart_json.get("type", "bar")
    data = chart_json.get("data", {})
    labels, values = data.get("labels", []), data.get("values", [])
    if not labels or not values: return None
    fig = px.pie(names=labels, values=values, title=title) if chart_type == "pie" else px.bar(x=labels, y=values, title=title)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig

def format_thinking_process(intermediate_steps: List) -> str:
    log = "### Agent Thinking Process\n\n"
    if not intermediate_steps: return log + "No intermediate steps."
    for action, observation in intermediate_steps:
        log += f"**Thought:** {str(action.log)}\n\n**Tool:** `{action.tool}`\n\n"
        log += f"**Input:**\n```sql\n{str(action.tool_input)}\n```\n\n"
        log += f"**Output:**\n```\n{str(observation)}\n```\n---\n"
    return log

def log_feedback(query: str, suggestions_json: str, selected_index: int, rating: float):
    try:
        if not query or not suggestions_json or selected_index is None:
            return gr.update(value="Could not log feedback: Missing context.", visible=True)
        suggestions_list = json.loads(suggestions_json)
        selected_question = suggestions_list[int(selected_index)]
        feedback_data = {"timestamp": [pd.Timestamp.now()], "query": [query], "suggested_question": [selected_question], "rating": [rating]}
        df = pd.DataFrame(feedback_data)
        file_exists = os.path.isfile(Config.FEEDBACK_LOG_FILE)
        df.to_csv(Config.FEEDBACK_LOG_FILE, mode='a', header=not file_exists, index=False)
        return gr.update(value=f"Feedback logged (Rating: {rating})", visible=True)
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return gr.update(value="Error logging feedback.", visible=True)

# --- AUTHENTICATION FUNCTIONS ---

def authenticate_user(username: str, password: str) -> tuple[bool, str]:
    """Authenticate user credentials"""
    if not username or not password:
        return False, "Please enter both username and password"
    
    if username in Config.USERS and Config.USERS[username] == password:
        return True, f"Welcome, {username}!"
    else:
        return False, "Invalid username or password"

def login_interface(username: str, password: str):
    """Handle login form submission"""
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

def logout_user():
    """Handle logout"""
    return (
        gr.update(visible=True),   # Show login form
        gr.update(visible=False),  # Hide main interface
        gr.update(value="Logged out successfully", visible=True),  # Show logout message
        ""  # Clear current user
    )

# --- 4. CORE AGENT AND UI LOGIC (CORRECTED YIELDS) ---

async def get_agent_response(message: str) -> Dict[str, Any]:
    result = await main_agent_executor.ainvoke({"input": message})
    full_response = result.get("output", "An error occurred.")
    parsed_output = {
        "text_answer": full_response, "chart_figure": None,
        "suggested_questions": [], "thinking_markdown": format_thinking_process(result.get("intermediate_steps", []))
    }
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

async def chat_ui_updater(message: str, history: List[Dict[str, str]]):
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": ""})
    
    # The number of items yielded must match the number of outputs (8 items)
    yield (history, gr.update(visible=False), gr.update(value="*Agent is thinking...*"),
           gr.Dataframe(value=[]), gr.update(visible=False), "",
           gr.Textbox(value=message), gr.Textbox())

    try:
        response = await get_agent_response(message)
        history[-1]["content"] = ""
        bot_message_so_far = ""
        for char in response["text_answer"]:
            bot_message_so_far += char
            history[-1]["content"] = bot_message_so_far
            yield (history, gr.update(), gr.update(), gr.update(), gr.update(),
                   "", gr.update(), gr.update())

        plot_update = gr.update(visible=False)
        if response["chart_figure"]:
            plot_update = gr.update(value=response["chart_figure"], visible=True)
        
        suggestions_list = response["suggested_questions"]
        dataframe_value = [[q] for q in suggestions_list]
        suggestions_box_update = gr.update(visible=True) if suggestions_list else gr.update(visible=False)
        
        yield (history, plot_update, response["thinking_markdown"],
               gr.Dataframe(value=dataframe_value), suggestions_box_update,
               "", gr.update(), json.dumps(suggestions_list))
               
    except Exception as e:
        print(f"An error occurred in chat_ui_updater: {e}")
        history[-1]["content"] = "Sorry, an error occurred. Please check the logs."
        yield (history, gr.update(), gr.update(value=f"Error: {e}"),
               gr.update(), gr.update(visible=False),
               "", gr.update(), gr.update())

# --- 5. GRADIO UI LAYOUT WITH AUTHENTICATION ---

with gr.Blocks(theme=gr.themes.Monochrome(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate"), title="FHIR RAG Chatbot") as demo:
    
    # State variables for authentication
    current_user = gr.State("")
    login_message = gr.Textbox(label="Status", visible=False, interactive=False)
    
    # Login Interface
    with gr.Group(visible=True) as login_form:
        gr.Markdown("# 🔐 Login Required")
        gr.Markdown("### Data Insights AI-Copilot (Sierra Leone FHIR Training Data)")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("")  # Spacer
            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("**Please log in to access the system:**")
                    username_input = gr.Textbox(
                        label="Username", 
                        placeholder="Enter your username",
                        max_lines=1
                    )
                    password_input = gr.Textbox(
                        label="Password", 
                        placeholder="Enter your password",
                        type="password",
                        max_lines=1
                    )
                    with gr.Row():
                        login_btn = gr.Button("Login", variant="primary", scale=2)
                        gr.Button("Clear", variant="secondary", scale=1).click(
                            lambda: ("", ""), 
                            outputs=[username_input, password_input]
                        )
            with gr.Column(scale=1):
                gr.Markdown("")  # Spacer
    
    # Main Application Interface (hidden by default)
    with gr.Group(visible=False) as main_interface:
        # Header with user info and logout
        with gr.Row():
            gr.Markdown("# Data Insights AI-Copilot (Sierra Leone FHIR Training Data)")
            with gr.Column(scale=1, min_width=200):
                user_display = gr.Markdown("", elem_classes=["user-info"])
                logout_btn = gr.Button("Logout", variant="secondary", size="sm")
        
        # Main chat interface
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(label="Chat History", type="messages")
                chat_progress = gr.Progress()
                textbox = gr.Textbox(placeholder="Ask a question...", container=False, scale=7)
                submit_btn = gr.Button("Send", variant="primary")
            with gr.Column(scale=2):
                plot = gr.Plot(label="Chart Visualization", visible=False)
                with gr.Accordion("Show Agent's Reasoning", open=False):
                    agent_progress = gr.Progress()
                    thinking_box = gr.Markdown(label="Agent's Thoughts", value="*Waiting for a question...*")

        # Suggestions and feedback section
        with gr.Group(visible=True) as suggestions_box:
            with gr.Row():
                suggestions_df = gr.Dataframe(
                    headers=["Suggested Questions"],
                    value=[["What is the total number of patients?"], 
                           ["Show the patient distribution by gender."], 
                           ["What are the top 5 most common conditions?"]],
                    col_count=(1, "fixed"), 
                    interactive=False, 
                    label="Suggestions (Select a row below to give feedback)",
                )
            with gr.Row():
                good_btn = gr.Button("Mark as Good 👍")
                bad_btn = gr.Button("Mark as Bad 👎")
            feedback_toast = gr.Textbox(label="Feedback Status", interactive=False, visible=False)

        # Hidden state variables
        last_query = gr.Textbox(visible=False)
        suggestions_store = gr.Textbox(visible=False)
        selected_suggestion_index = gr.Number(label="Selected Index", visible=False)
    
    # Login event handler
    def handle_login(username, password):
        is_valid, message = authenticate_user(username, password)
        
        if is_valid:
            return (
                gr.update(visible=False),  # Hide login form
                gr.update(visible=True),   # Show main interface
                gr.update(value=f"**Logged in as:** {username}", visible=True),  # Update user display
                username,  # Store current user
                "",  # Clear username field
                "",  # Clear password field
                gr.update(value="Login successful!", visible=False)  # Show success message
            )
        else:
            return (
                gr.update(visible=True),   # Keep login form visible
                gr.update(visible=False),  # Keep main interface hidden
                gr.update(value="", visible=False),  # Clear user display
                "",  # Clear current user
                username,  # Keep username (don't clear on failed login)
                "",  # Clear password
                gr.update(value=message, visible=True)  # Show error message
            )
    
    # Logout event handler
    def handle_logout():
        return (
            gr.update(visible=True),   # Show login form
            gr.update(visible=False),  # Hide main interface
            gr.update(value="", visible=False),  # Clear user display
            "",  # Clear current user
            "",  # Clear username
            "",  # Clear password
            gr.update(value="Logged out successfully", visible=True)  # Show logout message
        )
    
    # Event bindings for login/logout
    login_outputs = [login_form, main_interface, user_display, current_user, 
                    username_input, password_input, login_message]
    
    login_btn.click(
        handle_login,
        inputs=[username_input, password_input],
        outputs=login_outputs
    )
    
    # Allow Enter key to submit login
    password_input.submit(
        handle_login,
        inputs=[username_input, password_input], 
        outputs=login_outputs
    )
    
    logout_btn.click(
        handle_logout,
        outputs=login_outputs
    )
    
    # Chat functionality (only works when logged in)
    chat_outputs = [chatbot, plot, thinking_box, suggestions_df, suggestions_box, 
                   textbox, last_query, suggestions_store]
    
    async def submit_and_clear(message, history):
        async for update in chat_ui_updater(message, history):
            if history[-1]["content"] == "":
                chat_progress.visible = True
                agent_progress.visible = True
            else:
                chat_progress.visible = False
                agent_progress.visible = False
            yield update

    submit_btn.click(submit_and_clear, [textbox, chatbot], chat_outputs).then(lambda: "", None, textbox)
    textbox.submit(submit_and_clear, [textbox, chatbot], chat_outputs).then(lambda: "", None, textbox)

    # Suggestion handling
    def handle_suggestion_select(evt: gr.SelectData):
        log_feedback(last_query.value, suggestions_store.value, evt.index[0], 0.5)
        return evt.value, evt.index[0]
        
    suggestions_df.select(handle_suggestion_select, None, [textbox, selected_suggestion_index])
    good_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(1, visible=False)], [feedback_toast])
    bad_btn.click(log_feedback, [last_query, suggestions_store, selected_suggestion_index, gr.Number(-1, visible=False)], [feedback_toast])

if __name__ == "__main__":
    demo.launch()