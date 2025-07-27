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
from typing import Optional, List
import logging
import glob
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
os.environ["OPENAI_API_KEY"] = "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"

# Validate OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    logger.warning("OPENAI_API_KEY not found in environment variables")

app = FastAPI(title="FCA Handbook RAG Chatbot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://*.netlify.app",
        "https://*.netlify.com",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    return {"message": "OK"}

# Global variables
vectorstore = None
qa_chain = None
embeddings = None
processed_files = []  # Track uploaded files

# Define internal documents directory
INTERNAL_DOCS_DIR = "internal_documents"
ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.docx']

class QueryRequest(BaseModel):
    question: str
    
class QueryResponse(BaseModel):
    answer: str
    source_documents: Optional[list] = None

def initialize_embeddings():
    global embeddings
    if embeddings is None:
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
    return embeddings

def load_internal_documents():
    """Load all documents from the internal_documents directory"""
    global vectorstore, processed_files
    
    # Create internal documents directory if it doesn't exist
    os.makedirs(INTERNAL_DOCS_DIR, exist_ok=True)
    
    # Find all PDF files in the internal documents directory
    pdf_files = glob.glob(os.path.join(INTERNAL_DOCS_DIR, "*.pdf"))
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {INTERNAL_DOCS_DIR} directory")
        return False
    
    logger.info(f"Found {len(pdf_files)} PDF files to process")
    
    all_chunks = []
    all_texts = []
    all_metas = []
    
    try:
        for pdf_path in pdf_files:
            logger.info(f"Processing {pdf_path}")
            
            # Load and process each PDF
            loader = PyPDFLoader(pdf_path)
            docs = loader.load()
            
            splitter = CharacterTextSplitter(
                chunk_size=150, 
                chunk_overlap=25
            )
            chunks = splitter.split_documents(docs)
            
            # Add filename to metadata
            filename = os.path.basename(pdf_path)
            for chunk in chunks:
                chunk.metadata['source_file'] = filename
            
            all_chunks.extend(chunks)
            
            # Track processed file
            processed_files.append(filename)
        
        # Extract texts and metadata
        all_texts = [c.page_content for c in all_chunks if c.page_content.strip()]
        all_metas = [c.metadata for c in all_chunks if c.page_content.strip()]
        
        if not all_texts:
            raise ValueError("No valid text content found in any PDF")
        
        # Create vectorstore with all documents
        emb = initialize_embeddings()
        vectorstore = Chroma.from_texts(
            texts=all_texts, 
            embedding=emb, 
            metadatas=all_metas
        )
        
        logger.info(f"Created vectorstore with {len(all_chunks)} chunks from {len(pdf_files)} documents")
        return True
        
    except Exception as e:
        logger.error(f"Error loading internal documents: {str(e)}")
        return False

def create_vectorstore(pdf_path: str, chunk_size: int = 150, chunk_overlap: int = 25):
    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap
        )
        chunks = splitter.split_documents(docs)
        
        if not chunks:
            raise ValueError("No content could be extracted from the PDF")
        
        emb = initialize_embeddings()
        texts = [c.page_content for c in chunks if c.page_content.strip()]
        metas = [c.metadata for c in chunks if c.page_content.strip()]
        
        if not texts:
            raise ValueError("No valid text content found in PDF")
        
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

def add_to_vectorstore(pdf_path: str, existing_vectorstore, chunk_size: int = 150, chunk_overlap: int = 25):
    """Add new documents to existing vectorstore"""
    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap
        )
        chunks = splitter.split_documents(docs)
        
        texts = [c.page_content for c in chunks]
        metas = [c.metadata for c in chunks]
        
        # Add to existing vectorstore
        existing_vectorstore.add_texts(texts=texts, metadatas=metas)
        
        logger.info(f"Added {len(chunks)} chunks to existing vectorstore")
        return existing_vectorstore
        
    except Exception as e:
        logger.error(f"Error adding to vectorstore: {str(e)}")
        raise

def create_qa_chain(vectorstore, model_name: str = "gpt-3.5-turbo", temperature: float = 0.3):
    try:
        # Ensure API key is set
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key
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

@app.on_event("startup")
async def startup_event():
    """Load internal documents automatically when the app starts"""
    global qa_chain
    
    logger.info("Starting up - loading internal documents...")
    
    if load_internal_documents():
        qa_chain = create_qa_chain(vectorstore)
        logger.info("✅ Internal documents loaded successfully on startup")
    else:
        logger.info("⚠️ No internal documents found, system will wait for uploads")

@app.get("/")
async def root():
    return {"message": "FCA Handbook RAG Chatbot API", "status": "running"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "vectorstore_initialized": vectorstore is not None,
        "qa_chain_initialized": qa_chain is not None,
        "processed_files": processed_files,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "internal_docs_loaded": len(processed_files) > 0
    }

@app.post("/reload-internal-documents")
async def reload_internal_documents():
    """Reload all internal documents (useful for adding new docs without restart)"""
    global vectorstore, qa_chain, processed_files
    
    # Reset current state
    vectorstore = None
    qa_chain = None
    processed_files = []
    
    try:
        if load_internal_documents():
            qa_chain = create_qa_chain(vectorstore)
            return {
                "message": "Internal documents reloaded successfully",
                "documents_loaded": processed_files,
                "total_documents": len(processed_files)
            }
        else:
            raise HTTPException(
                status_code=404, 
                detail="No documents found in internal_documents directory"
            )
    except Exception as e:
        logger.error(f"Error reloading internal documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reloading documents: {str(e)}")

@app.post("/initialize-default")
async def initialize_default():
    """Initialize with default FCA combined handbook if it exists"""
    global vectorstore, qa_chain, processed_files
    
    # First try to load internal documents
    if load_internal_documents():
        qa_chain = create_qa_chain(vectorstore)
        return {
            "message": "System initialized with internal documents successfully",
            "documents": processed_files,
            "status": "ready"
        }
    
    # Fallback to looking for individual files in root directory
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
            detail="No documents found. Please add PDFs to the 'internal_documents' directory or upload a PDF document."
        )
    
    try:
        # Create vectorstore
        vectorstore = create_vectorstore(default_file)
        
        # Create QA chain
        qa_chain = create_qa_chain(vectorstore)
        
        # Track processed file
        processed_files = [default_file]
        
        logger.info(f"System initialized with default document: {default_file}")
        
        return {
            "message": "System initialized with FCA Combined Handbook successfully",
            "filename": default_file,
            "status": "ready"
        }
        
    except Exception as e:
        logger.error(f"Error initializing system: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error initializing system: {str(e)}")

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload PDF and add to knowledge base"""
    global vectorstore, qa_chain, processed_files
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        if vectorstore is None:
            # First PDF - create new vectorstore
            vectorstore = create_vectorstore(tmp_path)
            processed_files = [file.filename]
            message = "PDF uploaded and vectorstore created successfully"
        else:
            # Additional PDF - add to existing vectorstore
            vectorstore = add_to_vectorstore(tmp_path, vectorstore)
            processed_files.append(file.filename)
            message = "PDF uploaded and added to existing knowledge base"
        
        # Recreate QA chain with updated vectorstore
        qa_chain = create_qa_chain(vectorstore)
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        return {
            "message": message,
            "filename": file.filename,
            "total_documents": len(processed_files),
            "all_documents": processed_files
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
            detail="Please add documents to 'internal_documents' directory or upload a PDF first"
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

@app.delete("/clear-knowledge-base")
async def clear_knowledge_base():
    """Clear all uploaded documents and reset the system"""
    global vectorstore, qa_chain, processed_files
    
    vectorstore = None
    qa_chain = None
    processed_files = []
    
    return {
        "message": "Knowledge base cleared successfully",
        "status": "reset"
    }

@app.get("/documents")
async def list_documents():
    """List all processed documents"""
    return {
        "documents": processed_files,
        "count": len(processed_files),
        "vectorstore_initialized": vectorstore is not None
    }

@app.get("/internal-documents-status")
async def internal_documents_status():
    """Check what's in the internal documents directory"""
    internal_pdfs = glob.glob(os.path.join(INTERNAL_DOCS_DIR, "*.pdf"))
    return {
        "internal_documents_directory": INTERNAL_DOCS_DIR,
        "pdf_files_found": [os.path.basename(f) for f in internal_pdfs],
        "total_files": len(internal_pdfs),
        "directory_exists": os.path.exists(INTERNAL_DOCS_DIR)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))  # Cloud Run uses 8080
    uvicorn.run(app, host="0.0.0.0", port=port)