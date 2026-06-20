import ollama

SYSTEM_PROMPT = "You are ResumeAI, a professional resume screening and candidate analysis assistant. Your role is to help HR teams analyze resumes, compare candidates, and answer recruitment questions. For non-resume questions, politely redirect focus to resume analysis. Be professional and concise."

def get_ai_response(prompt: str) -> str:
    """Generates a chat response using Ollama."""
    try:
        response = ollama.chat(
            model="neural-chat:7b",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return response['message']['content']
    except Exception as e:
        print(f"Error generating AI response via Ollama: {e}")
        return "I'm having trouble processing your request right now. Please try again in a moment."