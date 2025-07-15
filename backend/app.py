from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI
import tempfile
import shutil
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(title="FCA Handbook RAG Chatbot", version="1.0.0")

# Add CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
vectorstore = None
qa_chain = None
embeddings = None

class QueryRequest(BaseModel):
    question: str
    
class QueryResponse(BaseModel):
    answer: str
    source_documents: Optional[list] = None

def initialize_embeddings():
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    return embeddings

def create_vectorstore(pdf_path: str, chunk_size: int = 300, chunk_overlap: int = 50):
    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap
        )
        chunks = splitter.split_documents(docs)
        
        emb = initialize_embeddings()
        texts = [c.page_content for c in chunks]
        metas = [c.metadata for c in chunks]
        
        vectorstore = Chroma.from_texts(
            texts=texts, 
            embedding=emb, 
            metadatas=metas
        )
        
        logger.info(f"Created vectorstore with {len(chunks)} chunks")
        return vectorstore
        
    except Exception as e:
        logger.error(f"Error creating vectorstore: {str(e)}")
        raise

def create_qa_chain(vectorstore, model_name: str = "gpt-3.5-turbo", temperature: float = 0.3):
    try:
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature
        )
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            chain_type="stuff",
            return_source_documents=True
        )
        
        logger.info("Created QA chain successfully")
        return qa_chain
        
    except Exception as e:
        logger.error(f"Error creating QA chain: {str(e)}")
        raise

@app.get("/")
async def root():
    return {"message": "FCA Handbook RAG Chatbot API", "status": "running"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "vectorstore_initialized": vectorstore is not None,
        "qa_chain_initialized": qa_chain is not None
    }

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    global vectorstore, qa_chain
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        vectorstore = create_vectorstore(tmp_path)
        qa_chain = create_qa_chain(vectorstore)
        
        os.unlink(tmp_path)
        
        return {
            "message": "PDF uploaded and processed successfully",
            "filename": file.filename
        }
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@app.post("/initialize-default")
async def initialize_default():
    """Initialize with default FCA combined handbook if it exists"""
    global vectorstore, qa_chain
    
    # Look for handbook/PDF
    possible_files = [
        "fca_combined_handbook.pdf",
        "combined_handbook.pdf", 
        "fca_handbook.pdf",
        "sample.pdf"  
    ]
    
    default_file = None
    for filename in possible_files:
        if os.path.exists(filename):
            default_file = filename
            break
    
    if not default_file:
        raise HTTPException(
            status_code=404, 
            detail="Default FCA handbook not found. Please upload a PDF document."
        )
    
    try:
        # Create vectorstore
        vectorstore = create_vectorstore(default_file)
        
        
        qa_chain = create_qa_chain(vectorstore)
        
        logger.info(f"System initialized with default document: {default_file}")
        
        return {
            "message": f"System initialized with FCA Combined Handbook successfully",
            "filename": default_file,
            "status": "ready"
        }
        
    except Exception as e:
        logger.error(f"Error initializing system: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error initializing system: {str(e)}")

# additional documents
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload additional PDF and add to existing knowledge base"""
    global vectorstore, qa_chain
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        
        new_vectorstore = create_vectorstore(tmp_path)
        
        
        vectorstore = new_vectorstore
        qa_chain = create_qa_chain(vectorstore)
        
        os.unlink(tmp_path)
        
        return {
            "message": "Additional PDF uploaded and processed successfully",
            "filename": file.filename,
            "note": "This document has been added to the knowledge base"
        }
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query_document(request: QueryRequest):
    global qa_chain
    
    if qa_chain is None:
        raise HTTPException(
            status_code=400, 
            detail="Please upload a PDF first to initialize the system"
        )
    
    try:
        result = qa_chain.invoke({"query": request.question})
        
        source_docs = []
        if "source_documents" in result:
            source_docs = [
                {
                    "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in result["source_documents"]
            ]
        
        return QueryResponse(
            answer=result["result"],
            source_documents=source_docs
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))  # Cloud Run uses port 8080
    uvicorn.run(app, host="0.0.0.0", port=port)