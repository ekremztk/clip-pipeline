from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.gemini_client import generate_json
from app.config import settings

router = APIRouter(prefix="/youtube-metadata", tags=["youtube-metadata"])


class GenerateRequest(BaseModel):
    title: str = ""
    description: str = ""
    guest_name: Optional[str] = None


class GenerateResponse(BaseModel):
    title: str
    description: str


@router.post("/generate", response_model=GenerateResponse)
async def generate_youtube_metadata(req: GenerateRequest):
    try:
        prompt = "You are a YouTube content optimization specialist.\n\n"
        prompt += "Generate an improved title and description for this video clip.\n\n"

        if req.title:
            prompt += "CURRENT TITLE: " + req.title + "\n"
        if req.description:
            prompt += "CURRENT DESCRIPTION: " + req.description + "\n"
        if req.guest_name:
            prompt += "GUEST NAME: " + req.guest_name + "\n"

        prompt += "\nRules:\n"
        prompt += "- Title: max 100 characters, compelling and click-worthy, include guest name if provided\n"
        prompt += "- Description: 2-4 short paragraphs, mention guest name, end with 5-8 relevant hashtags\n"
        prompt += "- Keep the same language as the original title/description\n"
        prompt += "- Return JSON with exactly two keys: 'title' and 'description'\n"

        result = generate_json(prompt, model=settings.GEMINI_MODEL_FLASH)

        return GenerateResponse(
            title=str(result.get("title", req.title)),
            description=str(result.get("description", req.description)),
        )

    except Exception as e:
        print(f"[YouTubeMetadata] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
