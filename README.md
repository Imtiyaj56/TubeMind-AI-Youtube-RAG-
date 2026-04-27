
# TubeMind-AI-Youtube-RAG-

# YouTube RAG — AI Video Assistant

An end-to-end, multilingual Retrieval-Augmented Generation (RAG) web application that allows you to chat interactively with any YouTube video. The application automatically fetches video transcripts, processes the text into a vector database, and uses advanced Language Models to answer your questions in real-time, streaming token-by-token directly into a premium user interface.

## 🌟 Key Features

- **Multilingual Support:** Seamlessly downloads transcripts in English, Hindi, or auto-generated captions depending on what is available on the video. If you ask a question in Hindi, the assistant replies in Hindi!
- **Contextual Document Compression:** Uses LangChain's `ContextualCompressionRetriever` and `MultiQueryRetriever` to extract the most critical parts of the transcript, reducing noise and drastically improving the precision of the answers.
- **Lightning-Fast Streaming Responses:** Leverages FastAPI and Server-Sent Events (SSE) to stream answers from the LLM back to the UI in real-time.
- **Premium User Interface:** A visually stunning, responsive dark-mode chat interface built using vanilla JavaScript, CSS variables, and HTML. Includes dynamic typing cursors, sidebar chat history, and scroll-to-bottom mechanics.
- **Open-Source Stack:** Uses `HuggingFaceEmbeddings` (MiniLM) for highly efficient local embedding generation and `FAISS` for fast, in-memory vector storage. Generative AI is powered by `llama-3.3-70b-versatile` over Groq.

## 🛠️ Technology Stack

- **Backend:** Python, FastAPI, SSE-Starlette
- **AI & RAG:** LangChain, FAISS, HuggingFace (`sentence-transformers`), Groq API, YouTube Transcript API
- **Frontend:** Vanilla JS, CSS3 (Custom Glassmorphism styling), HTML5

## ⚙️ Getting Started

### 1. Prerequisites

- Python 3.9 or higher
- A [Groq API Key](https://console.groq.com/keys) for the Llama-3.3 model.

### 2. Setup & Installation

Clone this repository and navigate into the folder:

```bash
git clone https://github.com/your-username/youtube-rag.git
cd youtube-rag
```

Create a virtual environment and install the required dependencies:

```bash
# Create and activate virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate
# On MacOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables

Create a file named `.env` in the root of the project to store your secret API keys safely:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 4. Running the Application

Start the FastAPI local server:

```bash
uvicorn app:app --reload
```

The server will spin up quickly. Open your web browser and navigate to:
**[http://localhost:8000](http://localhost:8000)**

## 💡 Usage Guide

1. Find a YouTube video you'd like to summarize or explore. Note the Video ID from the URL (e.g., `dQw4w9WgXcQ` in `watch?v=dQw4w9WgXcQ`).
2. Enter the Video ID on the left sidebar of the application and click **Process Video**.
3. Wait shortly for the background processing to download the transcript and generate the embedding vectors.
4. Begin chatting! Ask questions globally about the video context, ask for a quick summary, or pull out specific details.

## 🧠 Architecture Overview

The system architecture is decoupled beautifully between the RAG-engine and the API handler:

- `rag_multilingual.py`: Houses the LangChain pipeline logic. Handles the singleton loading of the embedding model, vector chunking (`RecursiveCharacterTextSplitter`), and creating the final output stream chain.
- `app.py`: Standardizes endpoints for the frontend. Serves HTML/CSS/JS statically and routes backend API requests (`/api/process_video` and `/api/ask`).
- `static/`: Contains the clean, YouTube-themed UI assets.

## 🤝 Contribution

Contributions are always welcome. Feel free to open an issue or submit a pull request if you want to add persistence (e.g., SQLite/PostgreSQL), add user authentication, or swap out the embedding models!

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

