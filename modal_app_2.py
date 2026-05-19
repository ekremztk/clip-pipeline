"""Second Modal GPU service deployment for S08/S09/S10.

Deploy with:
  MODAL_GPU_APP_NAME=gpu-pipeline_2 modal deploy modal_app_2.py

The implementation is shared with modal_app.py; only the Modal app name changes.
"""
from __future__ import annotations

import os

os.environ.setdefault("MODAL_GPU_APP_NAME", "gpu-pipeline_2")
os.environ.setdefault("MODAL_GPU_SECRET_NAME", "gpu-pipeline-secrets")

from modal_app import app

__all__ = ["app"]
