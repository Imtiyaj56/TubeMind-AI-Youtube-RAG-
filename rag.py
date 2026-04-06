# Import necessary modules for the RAG pipeline
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

# Load environment variables (like API keys)
load_dotenv()

# Global variables for caching the embedding model
_embedding_model = None

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
            model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
    return _embedding_model

def build_rag_pipeline(video_id: str) -> dict:
    """
    Builds and returns the LangChain RAG pipeline for a given YouTube video.
    Fetches the transcript, chunks it, creates a vector store, sets up document compression,
    and returns a ready-to-use LLM chain.
    """
    try:
        # Fetch the transcript for the video. Try English, Hindi, and auto-generated transcripts.
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=['en', 'hi', 'auto'])
        raw = fetched.to_raw_data()
        
        # Combine the transcript chunks into a single large string
        transcript = " ".join(chunk["text"] for chunk in raw)
    except TranscriptsDisabled:
        raise Exception("Transcripts are disabled for this video.")
    except Exception as e:
        raise Exception(f"Could not fetch transcript: {str(e)}")

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
