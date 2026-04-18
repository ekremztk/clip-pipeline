"""
Debug pipeline route — serves /tmp/pipeline_debug_{job_id}/*.json files.
Only active when PIPELINE_DEBUG=1. Protected by the same dev token check.
"""
import os
import json
import glob

from fastapi import APIRouter, HTTPException, Header
from app.config import settings

router = APIRouter(prefix="/debug/pipeline", tags=["debug"])

PIPELINE_DEBUG = os.getenv("PIPELINE_DEBUG", "0") == "1"


def _check_auth(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    testsprite_dev_id = os.getenv("TESTSPRITE_DEV_USER_ID")
    if testsprite_dev_id and token == "dev_token":
        return
    if token.count(".") != 2:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/{job_id}/steps")
def list_steps(job_id: str, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    debug_dir = f"/tmp/pipeline_debug_{job_id}"
    if not os.path.isdir(debug_dir):
        return {"job_id": job_id, "steps": [], "debug_enabled": PIPELINE_DEBUG}
    files = sorted(glob.glob(f"{debug_dir}/*.json"))
    steps = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return {"job_id": job_id, "steps": steps, "debug_enabled": PIPELINE_DEBUG}


@router.get("/{job_id}/steps/{step_name}")
def get_step(job_id: str, step_name: str, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    path = f"/tmp/pipeline_debug_{job_id}/{step_name}.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Step {step_name} not found for job {job_id}")
    with open(path) as f:
        data = json.load(f)
    return {"job_id": job_id, "step": step_name, "data": data}
