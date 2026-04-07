# Import necessary modules for the RAG pipeline
import os
import tempfile
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables (like API keys)
load_dotenv()

# Global variables for caching the embedding model and whisper model
_embedding_model = None
_whisper_model = None

# Initialize the Groq LLM (Llama 3.3 70B model)
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)

def get_embedding_model():
    """
    Helper function to load the HuggingFace embedding model.
    Uses a singleton pattern (global variable) to ensure the model is loaded only once.
    """
    global _embedding_model
    if _embedding_model is None:
        # Load the multilingual MiniLM model
        _embedding_model = HuggingFaceEmbeddings(
            model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
    return _embedding_model

def get_whisper_model():
    """
    Helper function to load the faster-whisper model.
    Uses a singleton pattern to avoid reloading the model on every fallback call.
    The 'base' model offers a good balance of speed and accuracy for CPU inference.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading faster-whisper 'base' model (first time may download ~150MB)...")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model

def get_transcript_fallback(video_id: str) -> str:
    """
    Fallback method: Downloads audio from a YouTube video using yt-dlp,
    then transcribes it locally using faster-whisper.
    The temporary audio file is deleted after transcription.
    """
    import yt_dlp

    logger.info(f"Fallback: Downloading audio for video '{video_id}' via yt-dlp...")

    # Create a temporary directory to store the downloaded audio
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "audio.m4a")

    # yt-dlp options: download best audio only, convert to m4a
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
    }

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        # Download the audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if not os.path.exists(output_path):
            raise FileNotFoundError("Audio download failed — file not found.")

        logger.info("Audio downloaded. Transcribing with faster-whisper...")

        # Transcribe the audio using faster-whisper
        model = get_whisper_model()
        segments, info = model.transcribe(output_path, beam_size=5)

        # Combine all transcribed segments into a single string
        transcript = " ".join(segment.text.strip() for segment in segments)

        logger.info(f"Transcription complete. Detected language: {info.language} "
                     f"(probability: {info.language_probability:.2f})")

        return transcript

    finally:
        # Clean up: delete the temporary audio file
        if os.path.exists(output_path):
            os.remove(output_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

def build_rag_pipeline(video_id: str) -> dict:
    """
    Builds and returns the LangChain RAG pipeline for a given YouTube video.
    Fetches the transcript, chunks it, creates a vector store, sets up document compression,
    and returns a ready-to-use LLM chain.

    Uses a hybrid approach:
      1. First tries the YouTube Transcript API (instant, no compute).
      2. If that fails, falls back to downloading audio via yt-dlp and
         transcribing locally with faster-whisper.
    """
    transcript = None

    api_error_msg = "None"
    # --- Strategy 1: YouTube Transcript API ---
    try:
        logger.info(f"Attempting to fetch transcript via YouTube API for video '{video_id}'...")
        # Corrected: Use get_transcript instead of fetch
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi', 'auto'])
        transcript = " ".join(item["text"] for item in transcript_list)
        logger.info("Transcript fetched successfully via YouTube API.")
    except Exception as e:
        api_error_msg = str(e)
        logger.warning(f"YouTube API failed: {api_error_msg}. Switching to Whisper fallback...")

    # --- Strategy 2: yt-dlp + faster-whisper fallback ---
    if not transcript:
        try:
            transcript = get_transcript_fallback(video_id)
        except Exception as fallback_error:
            raise Exception(
                f"Both transcript methods failed.\n"
                f"  YouTube API error: {api_error_msg}\n"
                f"  Whisper fallback error: {str(fallback_error)}"
            )

    if not transcript or not transcript.strip():
        raise Exception("Transcript is empty. The video may have no spoken content.")

   
   
   
   
   
    # ---------------------- Core RAG Pipeline ------------------------------

    # Initialize the recursive character text splitter to break transcript into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents([transcript])
    
    # Prepend 'passage: ' to each chunk for better passage retrieval with specific embeddings
    for doc in chunks:
        doc.page_content = "passage: " + doc.page_content

    # Create the FAISS vector store from the text chunks
    vector_store = FAISS.from_documents(documents=chunks, embedding=get_embedding_model())

    # Set up the MultiQueryRetriever to generate multiple variations of the user's query
    base_retriever = MultiQueryRetriever.from_llm(
        retriever=vector_store.as_retriever(
            search_type='mmr',
            search_kwargs={"k": 4, "lambda_mult": 0.5}
        ),
        llm=ChatGroq(model="llama-3.3-70b-versatile"),
    )
    
    # Use LLMChainExtractor to compress the retrieved documents, extracting only relevant information
    compressor = LLMChainExtractor.from_llm(llm)
    retriever = ContextualCompressionRetriever(
        base_retriever=base_retriever,
        base_compressor=compressor,
    )

    # Define the core Prompt Template to instruct the LLM
    template = PromptTemplate(
        template="""You are a helpful assistant and world-renowned subject matter expert.

Answer ONLY from the given context.
If the context is insufficient, say "I don't have enough information from this video to answer that."

IMPORTANT:
- Answer in the SAME language as the user's question.
- Be concise, clear, and well-structured.
- Use markdown formatting where appropriate (bold, lists, code blocks).

Question: {query}
Context: {context}
""",
        input_variables=["query", "context"],
    )

    def format_docs(docs):
        # Format documents by removing the 'passage: ' prefix added earlier
        return "\n\n".join(doc.page_content.replace("passage: ", "") for doc in docs)

    # Set up a RunnableParallel to process the query and context independently
    parallel_chain = RunnableParallel({
        "query": RunnablePassthrough(),
        "context": RunnableLambda(lambda x: "query: " + x) | retriever | RunnableLambda(format_docs),
    })
    
    # Create the string output parser
    parser = StrOutputParser()
    
    # Chain it all together: format inputs -> run prompt template -> query LLM -> parse output
    main_chain = parallel_chain | template | llm | parser

    return {"chain": main_chain}
