from datetime import datetime, timezone
from app.services.supabase_client import get_client
from app.models.enums import StepStatus

def log_pipeline_step(
    job_id: str,
    step_number: int,
    step_name: str,
    status: str,
    input_summary: dict | None = None,
    output_summary: dict | None = None,
    duration_ms: int | None = None,
    token_usage: dict | None = None,
    error_message: str | None = None,
    error_stack: str | None = None
) -> None:
    """
    Inserts a row into pipeline_audit_log table.
    never raises - full try/except
    """
    try:
        supabase = get_client()
        log_data = {
            "job_id": job_id,
            "step_number": step_number,
            "step_name": step_name,
            "status": status,
            "input_summary": input_summary or {},
            "output_summary": output_summary or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
            
        if token_usage is not None:
            log_data["token_usage"] = token_usage
            
        if error_message is not None:
            log_data["error_message"] = error_message
            
        if error_stack is not None:
            log_data["error_stack"] = error_stack
            
        supabase.table("pipeline_audit_log").insert(log_data).execute()
        print(f"[AuditLogger] Logged step {step_name} for job {job_id}: {status}")
    except Exception as e:
        print(f"[AuditLogger] Error logging step {step_name} for job {job_id}: {e}")

def get_job_cost(job_id: str) -> float:
    """
    Queries pipeline_audit_log WHERE job_id = job_id
    Sums all token_usage->>'cost_usd' values
    Returns total as float rounded to 4 decimal places, 0.0 on any failure
    """
    try:
        supabase = get_client()
        # Fetch all audit logs for the job to calculate cost
        response = supabase.table("pipeline_audit_log").select("token_usage").eq("job_id", job_id).execute()
        
        total_sum = 0.0
        if response.data:
            for row in response.data:
                token_usage = row.get("token_usage")
                if token_usage and isinstance(token_usage, dict):
                    cost = token_usage.get("cost_usd")
                    if cost is not None:
                        try:
                            total_sum = float(str(total_sum)) + float(str(cost))
                        except (ValueError, TypeError):
                            pass
                            
        # Return total as float rounded to 4 decimal places
        rounded_cost = int(total_sum * 10000) / 10000.0
        return rounded_cost
    except Exception as e:
        print(f"[AuditLogger] Error getting job cost for {job_id}: {e}")
        return 0.0

def get_job_audit_trail(job_id: str) -> list:
    """
    Queries pipeline_audit_log WHERE job_id = job_id ORDER BY step_number ASC
    Returns list of audit rows, [] on failure
    """
    try:
        supabase = get_client()
        response = supabase.table("pipeline_audit_log").select("*").eq("job_id", job_id).order("step_number").execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"[AuditLogger] Error getting audit trail for {job_id}: {e}")
        return []
