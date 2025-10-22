import os
from typing import List
import json
import ast
import sys

from flask import Flask, request, jsonify
from flask_cors import CORS

# LangChain Imports
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent, Tool
from langchain import hub

# Other Libraries
from sentence_transformers import SentenceTransformer

# --- FLASK APP SETUP ---
app = Flask(__name__)
CORS(app) # Allows the Superset frontend to call this API

# --- IMPORTANT: SET YOUR API KEYS HERE ---
api_key = os.getenv("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = api_key

# --- 0. CUSTOM EMBEDDING CLASS ---
class LocalHuggingFaceEmbeddings(Embeddings):
    def __init__(self, model_id):
        self.model = SentenceTransformer(model_id)
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()
    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()

# --- 1. SETUP THE DATABASE CONNECTION ---
DB_USER = "admin"
DB_PASSWORD = "admin"
DB_NAME = "views"
DB_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"

# --- THIS IS THE FIX: All tables are now included ---
all_tables = [
    "condition_flat", "diagnostic_report_flat", "encounter_flat",
    "immunization_flat", "location_flat", "medication_request_flat",
    "observation_flat", "organization_flat", "patient_flat",
    "practitioner_flat", "practitioner_role_flat", "procedure_flat"
]
db = SQLDatabase.from_uri(DB_URI, include_tables=all_tables)

# --- 2. SETUP ALL AGENT COMPONENTS (GLOBAL) ---
print("Loading all agent components...")
llm = ChatOpenAI(temperature=0, model_name="gpt-4o")
model_path = "./models/all-MiniLM-L6-v2"
embedding_model = LocalHuggingFaceEmbeddings(model_id=model_path)
persist_directory = 'chroma_db_index'

# --- Tool 1: RAG Tool ---
vector_db = Chroma(persist_directory=persist_directory, embedding_function=embedding_model)
rag_retriever = vector_db.as_retriever(search_kwargs={"k": 5})
rag_prompt = PromptTemplate.from_template(
    "Answer the user's question based only on the following context: Context: {context}\nQuestion: {question}"
)
rag_chain = RetrievalQA.from_chain_type(
    llm=llm, retriever=rag_retriever, chain_type_kwargs={"prompt": rag_prompt}
)

# --- Tool 2: SQL Tool ---
sql_agent = create_sql_agent(llm=llm, db=db, agent_type="openai-tools", verbose=True)

# --- Master Agent ---
tools = [
    Tool(
        name="semantic_patient_search", func=rag_chain.invoke,
        description="Use for general, semantic questions about patients/conditions.",
    ),
    Tool(
        name="database_query_agent", func=sql_agent.invoke,
        description="Use for questions about specific Patient IDs or for counting, aggregating, or calculating values.",
    ),
]
agent_prompt = hub.pull("hwchase17/openai-tools-agent")
main_agent = create_openai_tools_agent(llm, tools, agent_prompt)
main_agent_executor = AgentExecutor(agent=main_agent, tools=tools, verbose=True)
print("--- Master Chatbot API is Ready! ---")


# --- 3. DEFINE THE API ENDPOINT ---
@app.route('/ask', methods=['POST'])
def ask():
    """Receives a question and returns the agent's answer."""
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({"error": "No query provided"}), 400

    query = data['query']
    
    try:
        # Invoke the main agent executor with the user's query
        result = main_agent_executor.invoke({"input": query})
        answer = result.get("output", "Sorry, I encountered an issue.")
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run the Flask app on port 5001
    app.run(host='0.0.0.0', port=5001)