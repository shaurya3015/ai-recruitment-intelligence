import json
from qdrant_client import QdrantClient, models
import ollama

# --- Configuration ---
EMBEDDING_MODEL = "nomic-embed-text" # Switched to dedicated embedding model
COLLECTION_NAME = "resume-collection"
VECTOR_DIMENSION = 768  # Correct dimension size for nomic-embed-text

qdrant = QdrantClient(":memory:")
# --- End Configuration ---

def get_local_embedding(text):
    """Generates an embedding locally using Ollama."""
    try:
        response = ollama.embeddings(model=EMBEDDING_MODEL, prompt=text)
        return response['embedding']
    except Exception as e:
        print(f"Error generating local embedding: {e}")
        return None

if __name__ == "__main__":
    # Load the parsed resume summaries from the JSON file
    try:
        with open("parsed_resumes.json", "r", encoding="utf-8") as f:
            summaries = json.load(f)
    except FileNotFoundError:
        print("Error: 'parsed_resumes.json' not found.")
        exit()

    # Create the local Qdrant collection
    print(f"Creating local Qdrant collection '{COLLECTION_NAME}'...")
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=VECTOR_DIMENSION, distance=models.Distance.COSINE),
    )
    print("Collection created successfully.")

    points = []
    print(f"Generating local embeddings for {len(summaries)} summaries using Ollama...")
    for i, item in enumerate(summaries):
        summary_text = item.get("Summary")
        if not summary_text:
            continue
            
        vector = get_local_embedding(summary_text)
        
        if vector:
            points.append(models.PointStruct(
                id=i,
                vector=vector,
                payload={
                    "text": summary_text,
                    "file_name": item.get("FileName"),
                    "folder": item.get("Folder")
                }
            ))

    if points:
        print(f"Uploading {len(points)} vectors to local Qdrant instance...")
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True
        )
        print(f"✅ Success! Uploaded {len(points)} resume vectors locally.")
    else:
        print("No vectors were generated.")