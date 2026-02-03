import os
import io
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

app = FastAPI(title="Archi Multimodal Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.post("/forge")
async def forge_post(
    raw_text: str = Form(...),
    platform: str = Form(...),
    tone: str = Form(...),
    user_persona: str = Form(...),
    media_file: UploadFile = File(None)  
):
    try:
        # 1. PROMPT 
        if platform.lower() == "linkedin":
            format_rules = "Structure: The Hook (Line 1): Grab attention immediately with a question, surprising fact, or a bold statement to stop the scroll. The Problem/Context: Briefly explain the issue, experience, or topic. The Solution/Value (Body): Use 3-5 bullet points to make the content scannable. The Takeaway: Share a single, clear, actionable insight. Call to Action (CTA): End with a question or prompt to encourage comments (e.g., What are your thoughts?). Hashtags: Include 3-5 specific, relevant hashtags at the bottom. Use no markups like Bold and also give outputs such that I can directly copy and paste whole with no here's your post"
        elif platform.lower() == "instagram":
            format_rules = "Structure: Visual caption. Emojis. Block of hashtags at the bottom."
        else:
            format_rules = "Standard social post."

        system_instruction = f"""
        ACT AS: A social media expert writing for this persona: "{user_persona}".
        TASK: Write a {platform} post based on the text notes AND the attached image (if provided).
        GUIDE: {tone} tone. {format_rules}.
        RAW NOTES: "{raw_text}"
        """
        
        content_payload = [system_instruction]

        # 2. IMAGE PROCESSING
        if media_file:
            file_bytes = await media_file.read()
            image = Image.open(io.BytesIO(file_bytes))
            content_payload.append(image)
            content_payload.append("\n\n(Write the post specifically referencing details found in this image)")

        # 3. GENERATE
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", 
            contents=content_payload
        )
        
        return {"success": True, "output": response.text}

    except Exception as e:
        print(f"Multimodal Error: {e}")
        raise HTTPException(status_code=500, detail="Archi failed to process the media.")