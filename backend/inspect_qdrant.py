from qdrant_client import QdrantClient
import os

# --- Configuration ---
qdrant = QdrantClient(
    url="https://e3cd1f10-5a54-4c4f-9800-4893e289ad47.eu-central-1-0.aws.cloud.qdrant.io",
    api_key=os.environ.get("QDRANT_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.8l-4EOKd4SQGDSYTQB_jatdgoWF7JokKd6Hoz1TcrY0"),
)

COLLECTION_NAME = "resume-collection"
# --- End Configuration ---

if __name__ == "__main__":
    try:
        print(f"Inspecting collection: '{COLLECTION_NAME}'...")
        
        # Get collection info to verify vector size
        collection_info = qdrant.get_collection(collection_name=COLLECTION_NAME)
        
        print("\n--- Collection Info ---")
        # --- FIXED LINES ---
        # Access the vector configuration using the updated object structure
        print(f"Vector size: {collection_info.config.params.vectors.size}")
        print(f"Distance metric: {collection_info.config.params.vectors.distance}")
        print(f"Total points (resumes): {collection_info.points_count}")
        # --- END OF FIX ---
        
        # Scroll through some points to see the payload
        scroll_result = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=10, 
            with_payload=True,
            with_vectors=False # We don't need to see the long vector
        )

        print("\n--- Stored Payloads in Qdrant (First 10) ---\n")
        # The scroll_result is a tuple: (list_of_points, next_page_offset)
        points = scroll_result[0]

        if not points:
            print("The collection is empty or no points were retrieved.")
        else:
            for idx, point in enumerate(points, 1):
                print(f"{idx}. Point ID: {point.id}")
                payload = point.payload
                print(f"   File Name: {payload.get('file_name', 'N/A')}")
                print(f"   Folder: {payload.get('folder', 'N/A')}")
                text_preview = payload.get("text", "")
                # Clean up the preview text by removing extra newlines for better readability
                clean_preview = ' '.join(text_preview.split())
                print(f"   Summary Preview: {clean_preview[:250]}...\n")

    except Exception as e:
        print(f"\nAn error occurred while inspecting Qdrant.")
        print(f"Please check if the collection '{COLLECTION_NAME}' exists and that your Qdrant connection details are correct.")
        print(f"Error details: {e}")