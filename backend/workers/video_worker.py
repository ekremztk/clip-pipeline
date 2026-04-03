import traceback

from app.pipeline.orchestrator import run_pipeline


def start_pipeline(job_id: str, video_path: str, video_title: str,
                   guest_name: str | None, channel_id: str) -> None:
    """
    Simply calls run_pipeline with all params
    Wraps in try/except, prints [Worker] prefixed logs
    """
    try:
        print(f"[Worker] Starting pipeline for job {job_id}")
        run_pipeline(job_id, video_path, video_title, guest_name, channel_id)
        print(f"[Worker] Pipeline completed for job {job_id}")
    except Exception as e:
        print(f"[Worker] Error starting pipeline for job {job_id}: {e}")
        traceback.print_exc()


