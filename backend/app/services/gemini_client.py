import json
import os
import re
import time
import threading
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import settings

# ── Per-step token accumulator (thread-local, used by orchestrator) ──────────
_thread_local = threading.local()

def reset_token_accumulator() -> None:
    """Call before a pipeline step starts to begin fresh token tracking."""
    _thread_local.input_tokens = 0
    _thread_local.output_tokens = 0
    _thread_local.cost_usd = 0.0

def get_accumulated_token_usage() -> dict:
    """Returns accumulated token/cost for the current step and resets."""
    usage = {
        "input_tokens": getattr(_thread_local, "input_tokens", 0),
        "output_tokens": getattr(_thread_local, "output_tokens", 0),
        "cost_usd": round(getattr(_thread_local, "cost_usd", 0.0), 6),
    }
    reset_token_accumulator()
    return usage

def _accumulate_tokens(input_tokens: int | None, output_tokens: int | None, model: str) -> None:
    """Add token counts to the current step accumulator with rough cost estimate."""
    if not hasattr(_thread_local, "input_tokens"):
        reset_token_accumulator()
    inp = input_tokens or 0
    out = output_tokens or 0
    _thread_local.input_tokens += inp
    _thread_local.output_tokens += out
    # Rough Vertex AI pricing (estimates for display purposes)
    if "pro" in model.lower():
        cost = (inp / 1_000_000 * 1.25) + (out / 1_000_000 * 5.00)
    else:
        cost = (inp / 1_000_000 * 0.075) + (out / 1_000_000 * 0.30)
    _thread_local.cost_usd = getattr(_thread_local, "cost_usd", 0.0) + cost

# Langfuse — lazy init, no-op if not configured
_langfuse = None

def _get_langfuse():
    global _langfuse
    if _langfuse is None and settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse
            _langfuse = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
        except Exception as e:
            print(f"[GeminiClient] Langfuse init failed (non-critical): {e}")
    return _langfuse


def _trace_generation(
    name: str,
    model: str,
    prompt_input: str,
    output: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    metadata: dict | None = None,
):
    """Send a generation trace to Langfuse with token usage. Silent on failure."""
    try:
        lf = _get_langfuse()
        if not lf:
            return
        trace = lf.trace(name=name)
        usage = None
        if input_tokens is not None or output_tokens is not None:
            usage = {
                "input": input_tokens or 0,
                "output": output_tokens or 0,
                "total": (input_tokens or 0) + (output_tokens or 0),
                "unit": "TOKENS",
            }
        trace.generation(
            name=name,
            model=model,
            input=prompt_input,
            output=output if output else "",
            usage=usage,
            metadata=metadata or {},
        )
        lf.flush()
    except Exception as e:
        print(f"[GeminiClient] Langfuse trace failed (non-critical): {e}")

_gemini_client: Optional[genai.Client] = None
_developer_client: Optional[genai.Client] = None

def get_developer_client() -> genai.Client:
    """Returns a Gemini Developer client for file uploads (since files.upload is not supported in Vertex AI)."""
    global _developer_client
    if _developer_client is None:
        try:
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY is not set. Developer client requires an API key for file uploads.")
            _developer_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            print("[GeminiClient] Developer client initialized.")
        except Exception as e:
            print(f"[GeminiClient] Error initializing Developer client: {e}")
            raise
    return _developer_client

def get_gemini_client() -> genai.Client:
    """Lazy initialization of the Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        try:
            # DÜŞÜK-1: Use in-memory credentials instead of writing to temp file
            if settings.GCP_CREDENTIALS_JSON:
                from google.oauth2 import service_account
                creds_info = json.loads(settings.GCP_CREDENTIALS_JSON)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                _gemini_client = genai.Client(
                    vertexai=True,
                    project=settings.GCP_PROJECT,
                    location=settings.GCP_LOCATION,
                    credentials=credentials,
                )
            else:
                # Application Default Credentials fallback
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

    t0 = time.time()
    _last_response: list = []  # mutable container to capture response from closure

    def do_generate() -> str:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        _last_response.clear()
        _last_response.append(response)
        return str(response.text)

    result = str(_retry_logic(do_generate))
    duration_ms = int((time.time() - t0) * 1000)

    input_tokens = output_tokens = None
    if _last_response:
        usage = getattr(_last_response[0], "usage_metadata", None)
        if usage:
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)

    _accumulate_tokens(input_tokens, output_tokens, model)
    _trace_generation(
        name="generate_json" if json_mode else "generate",
        model=model,
        prompt_input=prompt,
        output=result,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        metadata={"json_mode": json_mode, "duration_ms": duration_ms},
    )
    return result

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

def analyze_video(video_path: str, prompt: str, model: Optional[str] = None, json_mode: bool = False) -> str:
    """
    Analyzes a video file with Gemini.
    If < 20MB, uses inline bytes (fast, no upload needed).
    If >= 20MB, uploads to GCS and uses gs:// URI, then generates.
    Deletes uploaded GCS file in finally block.
    Uses _retry_logic for rate limit handling.
    json_mode=True sets response_mime_type="application/json" for cleaner output.
    """
    if model is None:
        model = settings.GEMINI_MODEL_PRO
    gcs_uri = None
    t0 = time.time()

    video_config = types.GenerateContentConfig(
        response_mime_type="application/json"
    ) if json_mode else None

    try:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        client = get_gemini_client()

        _last_video_response: list = []

        if file_size_mb < 20:
            print(f"[GeminiClient] Video size {file_size_mb:.1f}MB < 20MB. Using inline bytes.")
            with open(video_path, "rb") as f:
                video_bytes = f.read()

            video_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")

            def do_generate_inline() -> str:
                response = client.models.generate_content(
                    model=model,
                    contents=[video_part, prompt],
                    config=video_config,
                )
                _last_video_response.clear()
                _last_video_response.append(response)
                return str(response.text)

            result = _retry_logic(do_generate_inline)
            out = str(result) if result else "{}"
            in_tok = out_tok = None
            if _last_video_response:
                u = getattr(_last_video_response[0], "usage_metadata", None)
                if u:
                    in_tok = getattr(u, "prompt_token_count", None)
                    out_tok = getattr(u, "candidates_token_count", None)
            _accumulate_tokens(in_tok, out_tok, model)
            _trace_generation("analyze_video", model, prompt, out,
                              input_tokens=in_tok, output_tokens=out_tok,
                              metadata={"file_size_mb": round(file_size_mb, 1), "mode": "inline",
                                        "duration_ms": int((time.time() - t0) * 1000)})
            return out

        else:
            # Primary: GCS upload (requires credentials)
            try:
                print(f"[GeminiClient] Video size {file_size_mb:.1f}MB >= 20MB. Uploading to GCS.")
                from google.cloud import storage
                import uuid

                gcs_creds = None
                if settings.GCP_CREDENTIALS_JSON:
                    from google.oauth2 import service_account as _sa
                    gcs_creds = _sa.Credentials.from_service_account_info(
                        json.loads(settings.GCP_CREDENTIALS_JSON)
                    )

                storage_client = storage.Client(project=settings.GCP_PROJECT, credentials=gcs_creds)
                bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)

                blob_name = f"video_{uuid.uuid4().hex}_{os.path.basename(video_path)}"
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(video_path)

                gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"
                print(f"[GeminiClient] Uploaded video to {gcs_uri}")

                video_part = types.Part.from_uri(file_uri=gcs_uri, mime_type="video/mp4")

                def do_generate_uploaded() -> str:
                    response = client.models.generate_content(
                        model=model,
                        contents=[video_part, prompt],
                        config=video_config,
                    )
                    _last_video_response.clear()
                    _last_video_response.append(response)
                    return str(response.text)

                result = _retry_logic(do_generate_uploaded)
                out = str(result) if result else "{}"
                in_tok = out_tok = None
                if _last_video_response:
                    u = getattr(_last_video_response[0], "usage_metadata", None)
                    if u:
                        in_tok = getattr(u, "prompt_token_count", None)
                        out_tok = getattr(u, "candidates_token_count", None)
                _accumulate_tokens(in_tok, out_tok, model)
                _trace_generation("analyze_video", model, prompt, out,
                                  input_tokens=in_tok, output_tokens=out_tok,
                                  metadata={"file_size_mb": round(file_size_mb, 1), "mode": "gcs",
                                            "duration_ms": int((time.time() - t0) * 1000)})
                return out
            except Exception as gcs_err:
                if gcs_uri:
                    raise  # GCS uploaded but generation failed — let outer except handle
                print(f"[GeminiClient] GCS upload failed ({gcs_err}). Falling back to File API...")

            # Fallback: Gemini File API via developer client (no extra credentials needed)
            uploaded_file_name = None
            dev_client_ref = None
            try:
                dev_client_ref = get_developer_client()
                response_file = dev_client_ref.files.upload(
                    file=video_path, config={"mime_type": "video/mp4"}
                )
                uploaded_file_name = response_file.name
                print(f"[GeminiClient] Uploaded to File API: {uploaded_file_name}")
                _poll_file_active(dev_client_ref, uploaded_file_name)

                file_video_part = types.Part.from_uri(
                    file_uri=response_file.uri, mime_type="video/mp4"
                )
                file_response = dev_client_ref.models.generate_content(
                    model=model,
                    contents=[file_video_part, prompt],
                    config=video_config,
                )
                out = str(file_response.text) if file_response.text else "{}"
                _trace_generation("analyze_video", model, prompt, out,
                                  metadata={"file_size_mb": round(file_size_mb, 1), "mode": "file_api",
                                            "duration_ms": int((time.time() - t0) * 1000)})
                return out
            except Exception as file_err:
                print(f"[GeminiClient] File API fallback also failed: {file_err}")
                return "{}"
            finally:
                if uploaded_file_name and dev_client_ref:
                    try:
                        dev_client_ref.files.delete(name=uploaded_file_name)
                        print(f"[GeminiClient] Deleted File API video: {uploaded_file_name}")
                    except Exception:
                        pass

    except Exception as e:
        print(f"[GeminiClient] Error in analyze_video: {e}")
        return "{}"
    finally:
        if gcs_uri:
            try:
                from google.cloud import storage
                storage_client = storage.Client(project=settings.GCP_PROJECT)
                bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
                blob_name = gcs_uri.split(f"gs://{settings.GCS_BUCKET_NAME}/")[1]
                blob = bucket.blob(blob_name)
                blob.delete()
                print(f"[GeminiClient] Deleted GCS video file {gcs_uri}")
            except Exception as cleanup_err:
                print(f"[GeminiClient] Warning: Failed to delete GCS file: {cleanup_err}")

def analyze_audio(audio_path: str, prompt: str, model: Optional[str] = None) -> str:
    """
    Analyzes an audio file.
    If < 20MB, uses inline bytes.
    If >= 20MB, uploads to GCS and uses gs:// URI, then generates.
    Deletes uploaded GCS file in finally block.
    """
    if model is None:
        model = settings.GEMINI_MODEL_FLASH
    gcs_uri = None
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
            print(f"[GeminiClient] Audio size {file_size_mb:.2f}MB >= 20MB. Uploading to GCS.")
            from google.cloud import storage
            import uuid
            
            storage_client = storage.Client(project=settings.GCP_PROJECT)
            bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
            
            blob_name = f"audio_{uuid.uuid4().hex}_{os.path.basename(audio_path)}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(audio_path)
            
            gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"
            print(f"[GeminiClient] Uploaded audio to {gcs_uri}")
            
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

            audio_part = types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type)
            
            def do_generate_uploaded() -> str:
                response = client.models.generate_content(
                    model=model,
                    contents=[audio_part, prompt]
                )
                return str(response.text)
                
            print(f"[GeminiClient] Generating content for uploaded audio...")
            result = _retry_logic(do_generate_uploaded)
            return str(result)
            
    except Exception as e:
        print(f"[GeminiClient] Error in analyze_audio: {e}")
        raise RuntimeError(f"analyze_audio failed: {e}")
    finally:
        if gcs_uri:
            try:
                print(f"[GeminiClient] Deleting GCS file {gcs_uri}...")
                from google.cloud import storage
                storage_client = storage.Client(project=settings.GCP_PROJECT)
                bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
                blob_name = gcs_uri.split(f"gs://{settings.GCS_BUCKET_NAME}/")[1]
                blob = bucket.blob(blob_name)
                blob.delete()
            except Exception as e:
                print(f"[GeminiClient] Error deleting GCS file {gcs_uri}: {e}")

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
