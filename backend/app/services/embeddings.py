import numpy as np
from fastembed import TextEmbedding

# Loaded once, on first use, then reused (loading the model takes a few seconds)
_embedding_model = None


def get_embedding_model():
    """
    Loads the all-MiniLM-L6-v2 embedding model once and reuses it on every later call.
    fastembed runs the same model through ONNX instead of PyTorch, which keeps
    memory low enough for small hosting instances (PyTorch alone needs 500MB+).
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _embedding_model


def embed_text(text: str) -> list:
    """Converts a piece of text into a numeric vector (embedding)."""
    model = get_embedding_model()
    return next(iter(model.embed([text]))).tolist()


def cosine_similarity(vector_a: list, vector_b: list) -> float:
    """
    Measures how similar two vectors are in direction.
    1.0 = essentially the same meaning, 0.0 = unrelated.
    This is the standard way to compare embeddings.
    """
    a = np.array(vector_a)
    b = np.array(vector_b)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


def compute_semantic_similarity(text_a: str, text_b: str) -> float:
    """
    Full pipeline: embeds both texts and returns their cosine similarity.
    Use this to compare candidate resume/skills text against a job description.
    """
    embedding_a = embed_text(text_a)
    embedding_b = embed_text(text_b)
    return cosine_similarity(embedding_a, embedding_b)
