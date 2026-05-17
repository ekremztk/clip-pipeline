from __future__ import annotations

from typing import Any

from app.config import settings


def _modal_client():
    token_id = settings.PROVISION_MODAL_TOKEN_ID
    token_secret = settings.PROVISION_MODAL_TOKEN_SECRET
    if not token_id or not token_secret:
        return None

    import modal

    return modal.Client.from_credentials(token_id, token_secret)


def render_variant_remote(
    *,
    input_video_url: str,
    plan: dict[str, Any],
    variant_id: str,
) -> dict[str, Any]:
    if not settings.PROVISION_MODAL_ENABLED:
        raise RuntimeError("Provision Modal rendering is disabled")

    import modal

    client = _modal_client()
    fn = modal.Function.from_name(
        settings.PROVISION_MODAL_APP_NAME,
        settings.PROVISION_MODAL_FUNCTION_NAME,
        client=client,
    )
    return fn.remote(
        input_video_url=input_video_url,
        plan=plan,
        variant_id=variant_id,
    )
