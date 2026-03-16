import json
import os
import re
import time
import tempfile
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import settings

_gemini_client: Optional[genai.Client] = None

def get_gemini_client() -> genai.Client:
    """Lazy initialization of the Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        try:
            if settings.GCP_CREDENTIALS_JSON:
                fd, temp_file_path = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, 'w') as f:
                    f.write(settings.GCP_CREDENTIALS_JSON)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file_path
                
            _gemini_client = genai.Client(vertexai=True, project=settings.GCP_PROJECT, location=settings.GCP_LOCATION)
            print(f"[GeminiClient] Vertex AI initialized for project {settings.GCP_PROJECT}")
        except Exception as e:
            print(f"[GeminiClient] Error initializing client: {e}")
            raise
    return _gemini_client

def _retry_logic(operation_func, *args, **kwargs) -> Any:
    """
    Helper to execute an operation with retry logic for rate limits.
    Max 3 attempts total.
    1st failure: sleep 30s
    2nd failure: sleep 60s
    3rd failure: raise RuntimeError
    """
    delays = [30, 60]
    for attempt in range(3):
        try:
            return operation_func(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            is_rate_limit = False
            
            # Check for 429 in Exception (APIError typically)
            if getattr(e, "code", None) == 429:
                is_rate_limit = True
            elif "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                is_rate_limit = True
                
            if is_rate_limit and attempt < 2:
                delay = delays[attempt]
                print(f"[GeminiClient] Rate limit hit (attempt {attempt + 1}/3). Sleeping for {delay}s...")
                time.sleep(delay)
            else:
                if attempt == 2 and is_rate_limit:
                    print(f"[GeminiClient] Error: Rate limit exhausted after 3 attempts.")
                    raise RuntimeError(f"Rate limit exhausted: {e}")
                
                print(f"[GeminiClient] Error in operation: {e}")
                raise

def _generate_internal(prompt: str, system: Optional[str] = None, json_mode: bool = False, model: Optional[str] = None) -> str:
    """Internal implementation for text and json generation."""
    client = get_gemini_client()
    if model is None:
        model = settings.GEMINI_MODEL_FLASH
    
    config_kwargs = {}
    if system:
        config_kwargs["system_instruction"] = system
        
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
        
    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
    
    def do_generate() -> str:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return str(response.text)
        
    return str(_retry_logic(do_generate))

def generate(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    """
    Generate text from a prompt.
    Retries on 429 (30s, 60s, then raise).
    """
    try:
        return str(_generate_internal(prompt, system=system, json_mode=False, model=model))
    except Exception as e:
        print(f"[GeminiClient] Error in generate: {e}")
        raise

def generate_json(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate JSON from a prompt.
    Retries on 429 (30s, 60s, then raise).
    Strips markdown formatting and parses JSON.
    """
    try:
        raw_text = _generate_internal(prompt, system=system, json_mode=True, model=model)
        if not raw_text:
            raise ValueError("Empty response received.")
            
        # Strip ```json wrappers
        cleaned = str(raw_text).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        cleaned = cleaned.strip()
        
        # Clean control chars
        cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned)
        
        return json.loads(cleaned)
    except Exception as e:
        print(f"[GeminiClient] Error in generate_json: {e}")
        raise ValueError(f"Failed to generate or parse JSON: {e}")

def _poll_file_active(client: genai.Client, file_name: str, max_attempts: int = 30, delay: int = 3):
    """Polls a file until its state becomes ACTIVE."""
    print(f"[GeminiClient] Polling file {file_name} for ACTIVE state...")
    for attempt in range(max_attempts):
        try:
            file_info = client.files.get(name=file_name)
            state = file_info.state.name if hasattr(file_info.state, "name") else str(file_info.state)
            
            if state == "ACTIVE":
                print(f"[GeminiClient] File {file_name} is ACTIVE.")
                return True
            elif state == "FAILED":
                print(f"[GeminiClient] Error: File {file_name} processing failed.")
                raise RuntimeError(f"File processing failed for {file_name}")
                
            print(f"[GeminiClient] File state is {state}. Waiting {delay}s... ({attempt + 1}/{max_attempts})")
            time.sleep(delay)
        except Exception as e:
            print(f"[GeminiClient] Error polling file {file_name}: {e}")
            if "not found" in str(e).lower():
                raise
            time.sleep(delay)
            
    print(f"[GeminiClient] Error: Timeout polling file {file_name} after {max_attempts} attempts.")
    raise RuntimeError(f"Timeout waiting for file {file_name} to become active")

def analyze_video(video_path: str, prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types
        import os
        
        client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT,
            location=settings.GCP_LOCATION
        )
        
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        print(f"[GeminiClient] Video size: {file_size_mb:.1f}MB, uploading...")
        
        # Upload file using Vertex AI Files API
        uploaded_file = client.files.upload(
            file=video_path,
            config=types.UploadFileConfig(mime_type="video/mp4")
        )
        
        print(f"[GeminiClient] File uploaded: {uploaded_file.name}")
        
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_PRO,
            contents=[
                types.Content(parts=[
                    types.Part.from_uri(
                        file_uri=uploaded_file.uri,
                        mime_type="video/mp4"
                    ),
                    types.Part.from_text(text=prompt)
                ])
            ]
        )
        
        # Clean up uploaded file
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass
        
        return response.text or "{}"
        
    except Exception as e:
        print(f"[GeminiClient] Error in analyze_video: {e}")
        return "{}"

def analyze_audio(audio_path: str, prompt: str, model: Optional[str] = None) -> str:
    """
    Analyzes an audio file.
    If < 20MB, uses inline bytes.
    If >= 20MB, uploads via Files API and polls.
    Deletes uploaded file if used.
    """
    if model is None:
        model = settings.GEMINI_MODEL_FLASH
    uploaded_file = None
    try:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        client = get_gemini_client()
        
        if file_size_mb < 20:
            print(f"[GeminiClient] Audio size {file_size_mb:.2f}MB < 20MB. Using inline bytes.")
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            
            # Use the correct MIME type based on extension, assuming common audio formats
            mime_type = "audio/mp3"
            ext = os.path.splitext(audio_path)[1].lower()
            if ext == ".m4a":
                mime_type = "audio/m4a"
            elif ext == ".wav":
                mime_type = "audio/wav"
            elif ext == ".ogg":
                mime_type = "audio/ogg"
            elif ext == ".mp4":
                mime_type = "audio/mp4"
                
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
            
            def do_generate_inline() -> str:
                response = client.models.generate_content(
                    model=model,
                    contents=[audio_part, prompt]
                )
                return str(response.text)
                
            print(f"[GeminiClient] Generating content for inline audio...")
            result = _retry_logic(do_generate_inline)
            return str(result)
            
        else:
            print(f"[GeminiClient] Audio size {file_size_mb:.2f}MB >= 20MB. Using Files API.")
            uploaded_file = client.files.upload(file=audio_path)
            print(f"[GeminiClient] Uploaded as {uploaded_file.name}")
            
            _poll_file_active(client, uploaded_file.name)
            
            def do_generate_uploaded() -> str:
                response = client.models.generate_content(
                    model=model,
                    contents=[uploaded_file, prompt]
                )
                return str(response.text)
                
            print(f"[GeminiClient] Generating content for uploaded audio...")
            result = _retry_logic(do_generate_uploaded)
            return str(result)
            
    except Exception as e:
        print(f"[GeminiClient] Error in analyze_audio: {e}")
        raise RuntimeError(f"analyze_audio failed: {e}")
    finally:
        if uploaded_file:
            try:
                print(f"[GeminiClient] Deleting uploaded file {uploaded_file.name}...")
                client = get_gemini_client()
                client.files.delete(name=uploaded_file.name)
            except Exception as e:
                print(f"[GeminiClient] Error deleting file {uploaded_file.name}: {e}")

def embed_content(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text using Gemini's text embedding model.
    Retries on 429 (30s, 60s, then raise).
    """
    try:
        client = get_gemini_client()
        
        def do_embed() -> list[float]:
            result = client.models.embed_content(
                model="text-embedding-004",
                contents=text
            )
            return result.embeddings[0].values
            
        return _retry_logic(do_embed)
    except Exception as e:
        print(f"[GeminiClient] Error in embed_content: {e}")
        raise ValueError(f"Failed to generate embedding: {e}")
