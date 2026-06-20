import ollama

client = ollama.Client(host='http://localhost:11434')

SYSTEM_PROMPT = "You are ResumeAI, a professional resume screening and candidate analysis assistant. Your role is to help HR teams analyze resumes, compare candidates, and answer recruitment questions. For non-resume questions, politely redirect focus to resume analysis. Be professional and concise."

def get_ai_response(prompt: str, history: list = None) -> str:
    """Generates a chat response using Ollama."""
    try:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]
        
        if history:
            for msg in history:
                if isinstance(msg, dict):
                    role = msg.get("role")
                    content = msg.get("content")
                else:
                    role = msg.role
                    content = msg.content
                messages.append({
                    "role": role,
                    "content": content,
                })
                
        messages.append({
            "role": "user",
            "content": prompt,
        })
        
        response = client.chat(
            model="neural-chat:7b",
            messages=messages,
        )
        return response['message']['content']
    except Exception as e:
        print(f"Error generating AI response via Ollama: {e}")
        return "I'm having trouble processing your request right now. Please try again in a moment."