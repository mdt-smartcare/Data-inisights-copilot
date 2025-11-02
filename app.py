import os
import gradio as gr
from dotenv import load_dotenv
import yaml
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

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

# Initialize LLM
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)

# Create the RAG prompt template
template = """Answer the question based on the following context. If you cannot answer the question based on the context, just say "I don't have enough information to answer that."

Context: {context}

Question: {question}

Please provide a clear, concise answer based only on the information in the context above. If multiple relevant records are found, summarize the key points."""

prompt = ChatPromptTemplate.from_template(template)

# Create the RAG chain
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

rag_chain = (
    {
        "context": lambda x: format_docs(retriever.query(x)),
        "question": RunnablePassthrough()
    }
    | prompt 
    | llm 
    | StrOutputParser()
)

# --- 2. CORE LOGIC ---
def process_query(question: str):
    if not question:
        return "", ""
    
    try:
        # Get the relevant documents
        retrieved_docs = retriever.query(question)
        
        # Format the context display
        formatted_context = "### Retrieved Context (Hybrid Search)\n\n"
        for i, doc in enumerate(retrieved_docs):
            source_table = doc.metadata.get('source_table', 'N/A')
            source_id = doc.metadata.get('source_id', 'N/A')
            formatted_context += f"**📄 Document {i+1} (Source: {source_table}, ID: {source_id})**\n"
            formatted_context += f"```\n{doc.page_content}\n```\n---\n"
        
        # Generate the answer using the LLM
        answer = rag_chain.invoke(question)
        
        final_answer = f"### Answer\n{answer}\n\n### Found {len(retrieved_docs)} relevant documents."
        
        return final_answer, formatted_context
    except Exception as e:
        return f"Error processing query: {str(e)}", ""

# --- 3. GRADIO UI ---
with gr.Blocks(theme=gr.themes.Soft(), title="Advanced RAG System") as demo:
    gr.Markdown("# Advanced RAG Query Interface")
    gr.Markdown("This interface uses **Small-to-Big Chunking**, **Hybrid Search**, and **GPT-3.5-Turbo** for generating answers.")
    
    with gr.Row():
        with gr.Column(scale=2):
            question_box = gr.Textbox(
                label="Your Question", 
                placeholder="e.g., show me records for young patients with high glucose"
            )
            submit_btn = gr.Button("Submit", variant="primary")
        with gr.Column(scale=3):
            answer_box = gr.Markdown(label="Answer")
            context_box = gr.Markdown(label="Retrieved Context")
            
    submit_btn.click(
        fn=process_query,
        inputs=[question_box],
        outputs=[answer_box, context_box]
    )

if __name__ == "__main__":
    demo.launch()