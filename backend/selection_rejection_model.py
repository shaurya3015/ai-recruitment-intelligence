import os
import json
import numpy as np
from scipy.spatial.distance import cosine
import docx2txt
from PyPDF2 import PdfReader
import google.generativeai as genai

# --- Configuration ---
# Configure your Gemini API key
# genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
genai.configure(api_key="AIzaSyCBJ6tEJM0KPCCMnJLGcYtbtkXttkih0rg") # Replace with your actual key
EMBEDDING_MODEL = "models/embedding-001"
# --- End Configuration ---

def get_gemini_embedding(text, task_type="RETRIEVAL_DOCUMENT"):
    """Generates an embedding for the given text using the Gemini API."""
    if not text or not text.strip():
        return None
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type=task_type,
        )
        return result['embedding']
    except Exception as e:
        print(f"  - Error generating embedding: {e}")
        return None

def extract_text_from_file(file_path):
    """Extracts text from PDF and DOCX files."""
    if file_path.lower().endswith(".pdf"):
        try:
            reader = PdfReader(file_path)
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
            return ""
    elif file_path.lower().endswith(".docx"):
        try:
            return docx2txt.process(file_path)
        except Exception as e:
            print(f"Error reading DOCX {file_path}: {e}")
            return ""
    elif file_path.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def load_and_embed_summaries(file_path):
    """Loads summaries from JSON and creates embeddings for them."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: JSON file '{file_path}' not found.")
        return [], []

    shortlisted_embeds = []
    rejected_embeds = []

    print("Generating embeddings for existing shortlisted and rejected resumes...")
    for entry in data:
        summary = entry.get("Summary", "").strip()
        folder = entry.get("Folder", "").lower()
        
        if not summary:
            continue
            
        embedding = get_gemini_embedding(summary)
        if embedding:
            if "shortlisted" in folder:
                shortlisted_embeds.append(embedding)
            elif "rejected" in folder:
                rejected_embeds.append(embedding)
                
    return np.array(shortlisted_embeds), np.array(rejected_embeds)

def decide_by_similarity(new_resume_embedding, shortlisted_embeds, rejected_embeds):
    """
    Calculates cosine similarity and decides whether to shortlist or reject.
    Note: Cosine similarity is 1 for identical, -1 for opposite. Distance is 1 - similarity.
    We find the *closest* match, which means the *minimum* cosine distance (or maximum similarity).
    """
    if new_resume_embedding is None:
        return "ERROR", 0, 0

    # Calculate cosine similarity (1 is most similar)
    sim_to_shortlisted = 1 - np.min([cosine(new_resume_embedding, emb) for emb in shortlisted_embeds])
    sim_to_rejected = 1 - np.min([cosine(new_resume_embedding, emb) for emb in rejected_embeds])

    print(f"  -> Similarity Score: Shortlisted={sim_to_shortlisted:.4f} | Rejected={sim_to_rejected:.4f}")

    if sim_to_shortlisted >= sim_to_rejected:
        return "SHORTLISTED", sim_to_shortlisted, sim_to_rejected
    else:
        return "REJECTED", sim_to_shortlisted, sim_to_rejected

def process_new_resumes(folder_path, shortlisted_embeds, rejected_embeds):
    """Processes each new resume in a folder and makes a decision."""
    if not os.path.isdir(folder_path):
        print(f"Error: New resume folder '{folder_path}' not found.")
        return

    print(f"\nScreening new resumes in '{folder_path}'...")
    for filename in os.listdir(folder_path):
        if not filename.lower().endswith((".pdf", ".docx", ".txt")):
            continue
            
        file_path = os.path.join(folder_path, filename)
        print(f"\n--- Processing: {filename} ---")
        
        resume_text = extract_text_from_file(file_path)
        if not resume_text.strip():
            print("  -> [Empty or unreadable resume file]")
            continue

        new_resume_embedding = get_gemini_embedding(resume_text, task_type="RETRIEVAL_QUERY")

        if new_resume_embedding and len(shortlisted_embeds) > 0 and len(rejected_embeds) > 0:
            decision, _, _ = decide_by_similarity(new_resume_embedding, shortlisted_embeds, rejected_embeds)
            print(f"  --> Decision: {decision}")
        else:
            print("  -> [Could not make a decision - check embeddings]")

if __name__ == "__main__":
    json_file = "parsed_resumes.json"
    new_resume_folder = "new_resumes"  # Create this folder and place new resumes inside

    # Step 1: Load existing resumes and create their embeddings
    shortlisted_embeddings, rejected_embeddings = load_and_embed_summaries(json_file)

    if shortlisted_embeddings.size == 0 or rejected_embeddings.size == 0:
        print("\nError: Could not proceed. Not enough embeddings from existing resumes.")
        print("Please ensure 'parsed_resumes.json' contains both 'Shortlisted' and 'Rejected' entries.")
    else:
        print(f"\nLoaded and embedded {len(shortlisted_embeddings)} shortlisted and {len(rejected_embeddings)} rejected summaries.")
        # Step 2: Process new resumes and compare them
        process_new_resumes(new_resume_folder, shortlisted_embeddings, rejected_embeddings)
        print("\n✅ Resume similarity screening complete.")