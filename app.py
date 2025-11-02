import os
import gradio as gr
from dotenv import load_dotenv
import yaml

# Load environment variables
load_dotenv()

from src.rag.retrieve import AdvancedRAGRetriever

# --- 1. CONFIGURATION and INITIALIZATION ---
print("Initializing Advanced RAG Query Application...")
with open("config/embedding_config.yaml", 'r') as f:
    config = yaml.safe_load(f)

# This initializes the entire chain: Chroma, Docstore, BM25, and Ensemble
retriever = AdvancedRAGRetriever(config)
print("✅ Application is ready to use!")


# --- 2. CORE LOGIC ---
def get_response(question: str):
    if not question:
        return "", ""

    # This single call now performs hybrid search
    results = retriever.query(question)
    
    # Format the response for Gradio UI
    formatted_context = "### Retrieved Context (Hybrid Search)\n\n"
    for i, doc in enumerate(results):
        source_table = doc.metadata.get('source_table', 'N/A')
        source_id = doc.metadata.get('source_id', 'N/A')
        formatted_context += f"**📄 Document {i+1} (Source: {source_table}, ID: {source_id})**\n"
        formatted_context += f"```\n{doc.page_content}\n```\n---\n"
    
    final_answer = f"Found {len(results)} relevant documents for your query. See the context below for details."
    
    return final_answer, formatted_context

# --- 3. GRADIO UI ---
with gr.Blocks(theme=gr.themes.Soft(), title="Advanced RAG System") as demo:
    gr.Markdown("# Advanced RAG Query Interface")
    # Updated title to be accurate
    gr.Markdown("This interface uses **Small-to-Big Chunking** and **Hybrid Search**.")
    
    with gr.Row():
        with gr.Column(scale=2):
            question_box = gr.Textbox(label="Your Question", placeholder="e.g., show me records for young patients with high glucose")
            submit_btn = gr.Button("Submit", variant="primary")
        with gr.Column(scale=3):
            answer_box = gr.Markdown(label="Final Answer")
            context_box = gr.Markdown(label="Retrieved Context")
            
    submit_btn.click(
        fn=get_response,
        inputs=[question_box],
        outputs=[answer_box, context_box]
    )

if __name__ == "__main__":
    demo.launch()