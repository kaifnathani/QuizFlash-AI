from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import json
import re
import base64
import google.generativeai as genai

# Load environment
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not set in .env file.")

genai.configure(api_key=GEMINI_API_KEY)
MODEL = genai.GenerativeModel("gemini-2.0-flash-exp")

app = FastAPI(title="Flashcard API", version="2.0.0")

def generate_quiz(prompt: str) -> list:
    """Call Gemini API and return quiz questions"""
    try:
        result = MODEL.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2048,
                response_mime_type="application/json"
            )
        )

        if result.candidates and result.candidates[0].content.parts:
            ai_reply = "".join(
                p.text for p in result.candidates[0].content.parts if hasattr(p, "text")
            )
        else:
            raise HTTPException(status_code=500, detail="Empty AI response")

        parsed = parse_json(ai_reply)
        quiz = parsed.get("quiz", [])

        validated = []
        for q in quiz:
            if isinstance(q, dict):
                question = q.get("question", "").strip()
                options = q.get("options", {})
                answer = q.get("answer", "").strip().lower()

                if (
                    question
                    and isinstance(options, dict)
                    and all(k in options for k in ["a", "b", "c", "d"])
                    and answer in ["a", "b", "c", "d"]
                ):
                    validated.append({
                        "question": question,
                        "options": options,
                        "answer": answer
                    })

        if not validated:
            raise HTTPException(status_code=500, detail="No valid quiz generated")

        return validated

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



def parse_json(text: str) -> dict:
    """Extract valid JSON from LLM response"""
    try:
        return json.loads(text)
    except:
        # Try to find JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                json_str = text[start:end+1]
                json_str = re.sub(r',\s*(\]|\})', r'\1', json_str)
                return json.loads(json_str)
            except:
                pass
    return {"flashcards": []}


def generate_flashcards(prompt: str) -> list:
    """Call Gemini API and return flashcards"""
    try:
        result = MODEL.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2048,
                response_mime_type="application/json"
            )
        )
        
        # Extract text
        if result.candidates and result.candidates[0].content.parts:
            ai_reply = "".join(p.text for p in result.candidates[0].content.parts if hasattr(p, "text"))
        else:
            raise HTTPException(status_code=500, detail="Empty AI response")
        
        # Parse JSON
        parsed = parse_json(ai_reply)
        flashcards = parsed.get("flashcards", [])
        
        # Validate
        validated = []
        for card in flashcards:
            if isinstance(card, dict):
                title = card.get("title", "").strip()
                content = card.get("content", "").strip()
                if title and content:
                    validated.append({"title": title, "content": content})
        
        if not validated:
            raise HTTPException(status_code=500, detail="No valid flashcards generated")
        
        return validated
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/flashcards/from-file")
async def flashcards_from_file(file: UploadFile = File(...)):
    """Generate flashcards from PDF/DOCX/PPTX file"""
    
    # Validate file type
    filename = file.filename.lower()
    if not (filename.endswith('.pdf') or filename.endswith('.docx') or filename.endswith('.pptx')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and PPTX files supported")
    
    # Read and encode file
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    if len(contents) > 15_000_000:  # 15MB limit
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")
    
    b64 = base64.b64encode(contents).decode('ascii')
    
    # Determine MIME type
    if filename.endswith('.pdf'):
        mime = "application/pdf"
    elif filename.endswith('.docx'):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    
    # Build prompt
    prompt = f"""Extract key concepts and create flashcards from this document.

Return ONLY valid JSON in this format:
{{
  "flashcards": [
    {{"title": "Concept title (3-8 words)", "content": "Clear explanation (1-3 sentences)"}}
  ]
}}

Rules:
- One concept per flashcard
- 5-25 flashcards based on content
- Factual and educational
- No markdown or special formatting

Document:
[BINARY_FILE]
MIME:{mime}
FILENAME:{filename}
BASE64_DATA:{b64}
[/BINARY_FILE]

Return only the JSON object."""
    
    flashcards = generate_flashcards(prompt)
    return {"flashcards": flashcards}


@app.post("/flashcards/from-text")
async def flashcards_from_text(text: str):
    """Generate flashcards from long text content"""
    
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    text = text.strip()
    if len(text) > 30_000:
        text = text[:30_000]
    

    prompt = f"""Extract key concepts and create flashcards from this text.

Return ONLY valid JSON in this format:
{{
  "flashcards": [
    {{"title": "Concept title (3-8 words)", "content": "Clear explanation (1-3 sentences)"}}
  ]
}}

Rules:
- One concept per flashcard
- 5-25 flashcards based on content
- Factual and educational
- No markdown or special formatting

Text:
\"\"\"{text}\"\"\"

Return only the JSON object."""
    
    flashcards = generate_flashcards(prompt)
    return {"flashcards": flashcards}


@app.post("/flashcards/from-title")
async def flashcards_from_title(title: str):
    """Generate detailed flashcards from topic title"""
    
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    title = title.strip()

    prompt = f"""Create educational flashcards for each topic below.

Return ONLY valid JSON in this format:
{{
  "flashcards": [
    {{"title": "Exact title from input", "content": "Educational explanation (2-4 sentences)"}}
  ]
}}

Rules:
- One flashcard per title
- Accurate and informative content
- Clear language for students
- No markdown or special formatting

Topics:
\"\"\"{title}\"\"\"

Return only the JSON object."""
    
    flashcards = generate_flashcards(prompt)
    return {"flashcards": flashcards}

@app.post("/quiz/from-file")
async def quiz_from_file(file: UploadFile = File(...), instruction: str = None):
    """Generate quiz questions (MCQs) from PDF/DOCX/PPTX file, optionally following teacher's instruction"""

    filename = file.filename.lower()
    if not (filename.endswith('.pdf') or filename.endswith('.docx') or filename.endswith('.pptx')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and PPTX files supported")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(contents) > 15_000_000:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")

    b64 = base64.b64encode(contents).decode('ascii')

    if filename.endswith('.pdf'):
        mime = "application/pdf"
    elif filename.endswith('.docx'):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    teacher_note = f"Teacher Instruction: {instruction}\n" if instruction else ""

    prompt = f"""
{teacher_note}
You are an expert educational content creator.

Generate a quiz in strict JSON format based on this document.

Return ONLY valid JSON in the following structure:
{{
  "quiz": [
    {{
      "question": "Meaningful question text?",
      "options": {{
        "a": "Option A",
        "b": "Option B",
        "c": "Option C",
        "d": "Option D"
      }},
      "answer": "a | b | c | d"
    }}
  ]
}}

Rules:
- no of multiple-choice questions : from instruction and if not provided, generate 5-15 questions
- Each question must be clear and concise
- Each question must have exactly 4 options (a–d)
- Only one correct answer per question
- Answer key should be one of: "a", "b", "c", "d"
- Questions must be factual, clear, and educational
- Do NOT use markdown or explanation text outside JSON
- Focus on key topics, definitions, and concepts from the document

Document:
[BINARY_FILE]
MIME:{mime}
FILENAME:{filename}
BASE64_DATA:{b64}
[/BINARY_FILE]

Return only the JSON object.
    """

    quiz = generate_quiz(prompt)
    return {"quiz": quiz}




@app.get("/")
async def root():
    """API information"""
    return {
        "name": "Flashcard API",
        "version": "2.0.0",
        "endpoints": {
            "POST /flashcards/from-file": "Upload PDF/DOCX/PPTX file",
            "POST /flashcards/from-text": "Send long text content",
            "POST /flashcards/from-title": "Send topic title"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)