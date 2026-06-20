from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams
import ollama

EMBEDDING_MODEL = "nomic-embed-text"
_qdrant_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path="./qdrant_storage")
    return _qdrant_client


def get_or_create_user_collection(user_id: int) -> str:
    """Create a Qdrant collection for each user."""
    collection_name = f"user_{user_id}"
    qdrant = get_qdrant_client()

    try:
        if qdrant.collection_exists(collection_name):
            return collection_name
    except Exception:
        try:
            qdrant.get_collection(collection_name)
            return collection_name
        except Exception:
            pass

    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    return collection_name


def _embed(text: str):
    client = ollama.Client(host='http://localhost:11434')
    response = client.embeddings(model=EMBEDDING_MODEL, prompt=text)
    return response["embedding"]


def embed_and_store_resume(
    user_id: int,
    resume_id: int,
    text: str,
    file_name: str = "",
    conversation_id: int | None = None,
) -> int | None:
    """Generate an embedding for a resume and store it in the user's collection.

    The point payload carries ``conversation_id`` so retrieval can be scoped to a
    single chat and never leak files from other conversations.
    """
    collection_name = get_or_create_user_collection(user_id)

    try:
        vector = _embed(text[:4000])
    except Exception as exc:
        print(f"Error generating embedding: {exc}")
        return None

    try:
        qdrant = get_qdrant_client()
        qdrant.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=resume_id,
                    vector=vector,
                    payload={
                        "resume_id": resume_id,
                        "conversation_id": conversation_id,
                        "file_name": file_name,
                        "text": text[:1000],
                        "full_text": text,
                    },
                )
            ],
        )
        return resume_id
    except Exception as exc:
        print(f"Error upserting to Qdrant: {exc}")
        return None


def search_user_resumes(
    user_id: int,
    query: str,
    limit: int = 5,
    resume_id: int | None = None,
    conversation_id: int | None = None,
):
    """Search within a user's resume collection, optionally scoped to one chat.

    When ``conversation_id`` is provided, only points uploaded in that conversation
    are searchable — files from other chats (or the older pre-scoping points that
    have no ``conversation_id`` in their payload) are excluded.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    collection_name = f"user_{user_id}"

    try:
        qdrant = get_qdrant_client()
        vector = _embed(query)

        must = []
        if resume_id is not None:
            must.append(FieldCondition(key="resume_id", match=MatchValue(value=resume_id)))
        if conversation_id is not None:
            must.append(FieldCondition(key="conversation_id", match=MatchValue(value=conversation_id)))
        query_filter = Filter(must=must) if must else None

        res = qdrant.query_points(
            collection_name=collection_name,
            query=vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=0.3,
            with_payload=True,
        )
        return res.points
    except Exception as exc:
        print(f"Error searching user collection: {exc}")
        return []


def delete_user_collection(user_id: int) -> None:
    collection_name = f"user_{user_id}"
    try:
        qdrant = get_qdrant_client()
        if qdrant.collection_exists(collection_name):
            qdrant.delete_collection(collection_name)
    except Exception as exc:
        print(f"Error deleting collection: {exc}")


def delete_resume_from_qdrant(user_id: int, resume_id: int) -> None:
    collection_name = f"user_{user_id}"
    try:
        qdrant = get_qdrant_client()
        qdrant.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=[resume_id]),
        )
    except Exception as exc:
        print(f"Error deleting resume from Qdrant: {exc}")
