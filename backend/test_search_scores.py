from qdrant_manager import search_user_resumes, get_qdrant_client, _embed
import sys

user_id = 3 # I don't know the exact user_id, but we can query qdrant directly

qdrant = get_qdrant_client()
collections = qdrant.get_collections().collections
for col in collections:
    print(f"Collection: {col.name}")
    # Let's search inside this collection without threshold
    vector = _embed("now check and tell me about Shaurya Varshney")
    res = qdrant.search(
        collection_name=col.name,
        query_vector=vector,
        limit=5,
        with_payload=True
    )
    for hit in res:
        print(f"  -> Score: {hit.score}, File: {hit.payload.get('file_name')}")
