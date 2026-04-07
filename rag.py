import os
import tempfile
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)
load_dotenv()

_embedding_model = None
_whisper_model = None

# LLM Model
LLM_MODEL = "llama-3.1-8b-instant"
llm = ChatGroq(model=LLM_MODEL, temperature=0.2)

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
    return _embedding_model

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model

def get_transcript_fallback(video_id: str) -> str:
    import yt_dlp
    logger.info(f"Fallback: Downloading audio for {video_id}...")
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "audio.m4a")
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'referer': 'https://www.youtube.com/',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    # ADDED: Support for optional cookies.txt to bypass YouTube blocks
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
        logger.info("Using cookies.txt for yt-dlp download...")
    
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        if not os.path.exists(output_path):
            raise FileNotFoundError("Audio download failed.")
        model = get_whisper_model()
        segments, info = model.transcribe(output_path, beam_size=5)
        return " ".join(segment.text.strip() for segment in segments)
    finally:
        if os.path.exists(output_path): os.remove(output_path)
        if os.path.exists(temp_dir): os.rmdir(temp_dir)

def build_rag_pipeline(video_id: str) -> dict:
    transcript = None
    api_error_msg = "None"

    try:
        logger.info(f"Trying API for {video_id}...")
        # Note: cookies.txt doesn't work easily here, so we rely on Whisper fallback more on HF
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi', 'auto'])
        transcript = " ".join(item["text"] for item in transcript_list)
        logger.info("Transcript fetched successfully via API.")
    except Exception as e:
        api_error_msg = str(e)
        logger.warning(f"API failed, switching to fallback...")

    if not transcript:
        try:
            transcript = get_transcript_fallback(video_id)
        except Exception as fallback_error:
            raise Exception(f"Failed to fetch content. Error: {str(fallback_error)}")

    # ---------------------- Core RAG Pipeline ----------------------
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents([transcript])
    for doc in chunks: 
        doc.page_content = "passage: " + doc.page_content

    emb_model = get_embedding_model()
    vector_store = FAISS.from_documents(documents=chunks, embedding=emb_model)
    
    # Use the 8B model for the retriever as well for speed
    base_retriever = MultiQueryRetriever.from_llm(
        retriever=vector_store.as_retriever(search_type='mmr', search_kwargs={"k": 4, "lambda_mult": 0.5}),
        llm=llm
    )
    
    compressor = LLMChainExtractor.from_llm(llm)
    retriever = ContextualCompressionRetriever(base_retriever=base_retriever, base_compressor=compressor)
    
    template = PromptTemplate(
        template="""You are a helpful subject matter expert. Answer ONLY from context. 
Answer in the SAME language as the question.

Question: {query}
Context: {context}
""",
        input_variables=["query", "context"]
    )

    def format_docs(docs):
        return "\n\n".join(doc.page_content.replace("passage: ", "") for doc in docs)

    parallel_chain = RunnableParallel({
        "query": RunnablePassthrough(),
        "context": RunnableLambda(lambda x: "query: " + x) | retriever | RunnableLambda(format_docs),
    })
    
    main_chain = parallel_chain | template | llm | StrOutputParser()
    return {"chain": main_chain}
