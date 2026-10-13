"""Turns text into vectors (lists of numbers) so passages can be found by meaning. Optional: without a
Gemini key the app simply uses keyword search."""
from app.core.config import get_settings


def embedding_tag() -> str:
    """Names the model + size. Stored with each passage so vectors from different models are never mixed."""
    s = get_settings()
    return f"{s.embedding_model.removeprefix('models/')}:{s.embedding_dimensions}"


def get_embeddings():
    """A LangChain embeddings object, or None when semantic search is off or no key is set."""
    s = get_settings()
    if not s.knowledge_semantic or not s.google_api_key:
        return None
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings(model=f"models/{s.embedding_model.removeprefix('models/')}",
                                        google_api_key=s.google_api_key,
                                        output_dimensionality=s.embedding_dimensions)
