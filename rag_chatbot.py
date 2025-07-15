import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI

# ---------- Load environment and PDF -----------

load_dotenv()

loader = PyPDFLoader("sample.pdf")
docs = loader.load()
splitter = CharacterTextSplitter(chunk_size=300, chunk_overlap=50)
chunks = splitter.split_documents(docs)

emb = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
texts = [c.page_content for c in chunks]
metas = [c.metadata for c in chunks]
vectorstore = Chroma.from_texts(texts=texts, embedding=emb, metadatas=metas)

# ---------- Use OpenAI GPT for LLM -----------

llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0.3
)

qa = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
    chain_type="map_reduce",
    chain_type_kwargs={"verbose": True}
)

print("Ready! Ask questions (type 'exit')\n")
while True:
    q = input(">> ")
    if q.lower() in {"exit","quit"}:
        break
    resp = qa.invoke({"query": q})
    print("\nAnswer:", resp["result"], "\n")
