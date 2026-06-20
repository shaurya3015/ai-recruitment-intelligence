import os
import json
import docx2txt
from PyPDF2 import PdfReader
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite"))

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
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading TXT {file_path}: {e}")
            return ""
    else:
        return ""

def summarize_resume_with_gemini(text, folder_name):
    """Generates a resume summary using the Gemini model."""
    if model is None:
        return f"{text[:3000]}\nStatus: {folder_name}"

    system_prompt = """
You are a professional resume summarizer. Your task is to extract key information from the provided resume text.

Please extract the following details:
- Full Name
- Location (City, State/Country)
- Contact Info (Email, Phone Number)
- Education (List all degrees and colleges)
- Work Experience (List all companies and job titles)
- Skills (Categorize into Technical and Soft Skills if possible)
- Status (This should be 'Shortlisted' or 'Rejected' based on the folder name provided)

Present the output as clean, readable text. Use bullet points for lists. Do not return JSON or Markdown formatting.
"""

    human_prompt = f"""Resume Text:
---
{text}
---

Folder Name: {folder_name}
"""
    
    full_prompt = f"{system_prompt}\n\n{human_prompt}"

    try:
        response = model.generate_content(full_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating summary with Gemini: {e}")
        return f"Error: Could not summarize. Gemini API call failed.\nStatus: {folder_name}"


def append_to_output_file(file_name, summary, output_path):
    """Appends the generated summary to a text file."""
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n===== {file_name} =====\n")
        f.write(summary)
        f.write("\n" + "=" * 50 + "\n")

def parse_summary_to_dict(summary, file_name, folder_name):
    """Creates a dictionary from the summary details."""
    return {
        "FileName": file_name,
        "Folder": folder_name,
        "Summary": summary
    }

def process_resume_folders(folders, output_txt_file, json_list):
    """Iterates through folders, processes resumes, and saves the output."""
    for folder_path in folders:
        if not os.path.isdir(folder_path):
            print(f"Warning: Folder '{folder_path}' not found. Skipping.")
            continue
            
        folder_name = os.path.basename(folder_path)
        all_files = os.listdir(folder_path)

        print(f"\nParsing folder: {folder_path}")
        for file_name in all_files:
            if not file_name.lower().endswith((".pdf", ".docx")):
                continue

            full_path = os.path.join(folder_path, file_name)
            print(f"  -> Processing: {file_name}")

            try:
                text = extract_text_from_file(full_path)
                if not text.strip():
                    print(f"     - Warning: No text extracted from {file_name}.")
                    continue
                
                summary = summarize_resume_with_gemini(text, folder_name)
                name_without_ext = os.path.splitext(file_name)[0]

                append_to_output_file(name_without_ext, summary, output_txt_file)

                parsed_dict = parse_summary_to_dict(summary, name_without_ext, folder_name)
                json_list.append(parsed_dict)

            except Exception as e:
                print(f"     - Error processing {file_name}: {e}")

if __name__ == "__main__":
    # Define folder paths and output file names
    shortlisted_folder = "ShortlistedDS"
    rejected_folder = "RejectedDS"
    output_txt = "parsed_resumes.txt"
    output_json = "parsed_resumes.json"

    # Ensure output files are cleared before starting
    open(output_txt, "w").close()

    json_results = []
    
    # Process both shortlisted and rejected resume folders
    process_resume_folders([shortlisted_folder, rejected_folder], output_txt, json_results)

    # Save the structured data to a JSON file
    with open(output_json, "w", encoding="utf-8") as jf:
        json.dump(json_results, jf, indent=4)

    print(f"\n✅ All summaries have been saved to: {output_txt}")
    print(f"✅ Structured JSON data saved to: {output_json}")
