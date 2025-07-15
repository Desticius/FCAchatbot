#!/bin/bash

echo "🏗️  Setting up FCA RAG Chatbot project structure..."
echo "=================================================="

# Create main directories
mkdir -p backend
mkdir -p frontend/src
mkdir -p frontend/public
mkdir -p infrastructure/terraform
mkdir -p .github/workflows

echo "📁 Created directory structure"

# Backend files
echo "⚙️  Creating backend files..."

# Main FastAPI app
cat > backend/app.py << 'EOF'
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

# Add CORS middleware
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
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
EOF

# Backend requirements
cat > backend/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
python-dotenv==1.0.0
langchain==0.1.0
langchain-community==0.0.10
langchain-openai==0.0.2
langchain-chroma==0.1.0
langchain-huggingface==0.0.1
chromadb==0.4.18
pypdf==3.17.4
sentence-transformers==2.2.2
pydantic==2.5.0
transformers==4.36.0
torch==2.1.0
EOF

# Backend Dockerfile
cat > backend/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
EOF

# Backend .env template
cat > backend/.env.example << 'EOF'
OPENAI_API_KEY=your_openai_api_key_here
HUGGINGFACE_API_TOKEN=your_huggingface_token_here
PORT=8000
EOF

echo "✅ Backend files created"

# Frontend files
echo "🎨 Creating frontend files..."

# Frontend package.json
cat > frontend/package.json << 'EOF'
{
  "name": "fca-rag-frontend",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "lucide-react": "^0.263.1"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  },
  "proxy": "http://localhost:8000"
}
EOF

# Frontend public/index.html
cat > frontend/public/index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta name="description" content="FCA Handbook RAG Chatbot" />
    <title>FCA RAG Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>
EOF

# Frontend src/index.js
cat > frontend/src/index.js << 'EOF'
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
EOF

# Frontend src/App.js (simplified version that works)
cat > frontend/src/App.js << 'EOF'
import React, { useState, useRef, useEffect } from 'react';

const FCAHandbookChat = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState('not_initialized');
  const [isUploading, setIsUploading] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  useEffect(() => {
    setMessages([{
      id: 1,
      type: 'system',
      content: 'Welcome to the FCA Handbook RAG Chatbot! Please upload a PDF document to get started.',
      timestamp: new Date()
    }]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE_URL}/upload-pdf`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      
      if (response.ok) {
        setSystemStatus('initialized');
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: `✅ Successfully uploaded and processed "${file.name}". You can now ask questions about the document.`,
          timestamp: new Date()
        }]);
      } else {
        throw new Error(data.detail || 'Upload failed');
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: `❌ Error uploading file: ${error.message}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;
    if (systemStatus !== 'initialized') {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: 'Please upload a PDF document first.',
        timestamp: new Date()
      }]);
      return;
    }

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: inputMessage }),
      });

      const data = await response.json();

      if (response.ok) {
        const botMessage = {
          id: Date.now() + 1,
          type: 'bot',
          content: data.answer,
          sources: data.source_documents || [],
          timestamp: new Date()
        };
        setMessages(prev => [...prev, botMessage]);
      } else {
        throw new Error(data.detail || 'Query failed');
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'error',
        content: `Error: ${error.message}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const MessageBubble = ({ message }) => {
    const isUser = message.type === 'user';
    const isSystem = message.type === 'system';
    const isError = message.type === 'error';

    return (
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
        <div className={`max-w-3xl px-4 py-2 rounded-lg ${
          isUser 
            ? 'bg-blue-500 text-white' 
            : isSystem 
              ? 'bg-gray-100 text-gray-700 border-l-4 border-blue-500' 
              : isError
                ? 'bg-red-50 text-red-700 border-l-4 border-red-500'
                : 'bg-gray-50 text-gray-800'
        }`}>
          <div className="whitespace-pre-wrap">{message.content}</div>
          {message.sources && message.sources.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-200">
              <div className="text-sm font-medium mb-2">Sources:</div>
              {message.sources.map((source, index) => (
                <div key={index} className="text-sm bg-white p-2 rounded mb-1">
                  <div className="font-medium">Page {source.metadata?.page || 'Unknown'}</div>
                  <div className="text-gray-600">{source.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">FCA Handbook RAG Chatbot</h1>
            <p className="text-sm text-gray-600">Ask questions about your uploaded documents</p>
          </div>
          <div className="flex items-center space-x-4">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".pdf"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {isUploading ? 'Uploading...' : 'Upload PDF'}
            </button>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="flex justify-start mb-4">
              <div className="bg-gray-50 px-4 py-2 rounded-lg">
                <span className="text-gray-600">Thinking...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="bg-white border-t px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center space-x-4">
            <input
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Ask a question about the uploaded document..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || !inputMessage.trim() || systemStatus !== 'initialized'}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FCAHandbookChat;
EOF

# Frontend Dockerfile
cat > frontend/Dockerfile << 'EOF'
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=0 /app/build /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
EOF

echo "✅ Frontend files created"

# Root level files
echo "📄 Creating root level files..."

# Main .gitignore
cat > .gitignore << 'EOF'
# Environment variables
.env
backend/.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
frontend/build/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# ChromaDB
chroma_db/

# Uploads
uploads/
EOF

# Docker compose for local development
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./backend:/app
      - ./uploads:/app/uploads
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000
    depends_on:
      - backend
    restart: unless-stopped
EOF

# Procfile for Railway/Heroku
cat > Procfile << 'EOF'
web: cd backend && python app.py
EOF

# Railway deployment file
cat > railway.json << 'EOF'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "backend/Dockerfile"
  },
  "deploy": {
    "startCommand": "cd backend && python app.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
EOF

# README
cat > README.md << 'EOF'
# FCA Handbook RAG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot for querying FCA handbook documents using LangChain, FastAPI, and React.

## Features

- Upload PDF documents
- Ask questions about uploaded content
- AI-powered responses with source citations
- Modern React frontend
- FastAPI backend with automatic API documentation

## Quick Start

### Local Development

1. **Backend Setup:**
   ```bash
   cd backend
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env with your OpenAI API key
   python app.py
   ```

2. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   npm start
   ```

3. **Access the app:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Docker Development

```bash
docker-compose up
```

## Environment Variables

Create `backend/.env`:
```
OPENAI_API_KEY=your_openai_api_key_here
```

## Deployment

### Railway (Free Tier)
1. Connect GitHub repo to Railway
2. Add OPENAI_API_KEY environment variable
3. Deploy automatically

### Other Platforms
- Google Cloud Run
- AWS ECS
- Azure Container Apps

See deployment configs in `/infrastructure` folder.

## Project Structure

```
FCAchatbot/
├── backend/           # FastAPI backend
├── frontend/          # React frontend
├── infrastructure/    # Deployment configs
└── README.md
```

## API Endpoints

- `POST /upload-pdf` - Upload and process PDF
- `POST /query` - Ask questions about documents
- `GET /health` - Health check
- `GET /docs` - API documentation

## License

MIT License
EOF

echo "✅ Root files created"

# Create GitHub Actions workflow
cat > .github/workflows/deploy.yml << 'EOF'
name: Deploy to Railway

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to Railway
      uses: bltavares/actions-railway@v1
      with:
        railway-token: ${{ secrets.RAILWAY_TOKEN }}
        command: railway up
EOF

echo "✅ GitHub Actions workflow created"

echo ""
echo "🎉 Project structure created successfully!"
echo ""
echo "📁 Your FCAchatbot folder now contains:"
echo "   ├── backend/          (FastAPI app)"
echo "   ├── frontend/         (React app)"
echo "   ├── infrastructure/   (Deployment configs)"
echo "   ├── .github/          (CI/CD workflows)"
echo "   ├── docker-compose.yml"
echo "   ├── README.md"
echo "   └── .gitignore"
echo ""
echo "🚀 Next steps:"
echo "1. cd FCAchatbot"
echo "2. Set up your OpenAI API key:"
echo "   cp backend/.env.example backend/.env"
echo "   # Edit backend/.env with your API key"
echo "3. Test locally:"
echo "   cd backend && pip install -r requirements.txt && python app.py"
echo "4. Deploy to Railway (free):"
echo "   - Push to GitHub"
echo "   - Connect repo to Railway"
echo "   - Add OPENAI_API_KEY environment variable"
echo ""
echo "💡 Your chatbot will be ready to use!"
EOF

# Make script executable
chmod +x setup_project.sh

echo "✅ Setup script created! Run it with:"
echo "   chmod +x setup_project.sh"
echo "   ./setup_project.sh"
