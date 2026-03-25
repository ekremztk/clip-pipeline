"""
Director Execution Planner — turns recommendations into actionable step-by-step plans.
When Director identifies an improvement, this module generates concrete implementation steps
with file paths, risk levels, and expected impact.
"""

from app.services.supabase_client import get_client
from app.director.tools.database import _run_sql


# Known file mappings for common recommendation areas
FILE_MAP = {
    "s05": "backend/app/pipeline/steps/s05_unified_discovery.py",
    "s06": "backend/app/pipeline/steps/s06_batch_evaluation.py",
    "s07": "backend/app/pipeline/steps/s07_precision_cut.py",
    "s08": "backend/app/pipeline/steps/s08_export.py",
    "channel_dna": "backend/app/channels/",
    "director": "backend/app/director/agent.py",
    "proactive": "backend/app/director/proactive.py",
    "learning": "backend/app/director/learning.py",
    "orchestrator": "backend/app/pipeline/orchestrator.py",
    "config": "backend/app/config.py",
    "prompts": "backend/app/pipeline/prompts/",
}


def create_execution_plan(recommendation_id: str) -> dict:
    """
    Generate a step-by-step implementation plan for a recommendation.
    Reads the recommendation from DB, analyzes the context, and produces
    ordered steps with file paths, actions, and risk assessments.
    """
    try:
        client = get_client()
        rec_res = client.table("director_recommendations").select("*").eq("id", recommendation_id).single().execute()
        if not rec_res.data:
            return {"error": f"Recommendation {recommendation_id} not found"}

        rec = rec_res.data
        title = rec.get("title", "")
        description = rec.get("description", "")
        module = rec.get("module_name", "")
        priority = rec.get("priority", 3)

        steps = _generate_steps(title, description, module)
        total_risk = _assess_total_risk(steps)

        plan = {
            "recommendation_id": recommendation_id,
            "title": title,
            "module": module,
            "priority": priority,
            "steps": steps,
            "total_risk": total_risk,
            "expected_impact": _estimate_impact(title, description, priority),
            "prerequisites": _check_prerequisites(steps),
        }

        client.table("director_recommendations").update({
            "dismissed_reason": f"Execution plan generated with {len(steps)} steps",
        }).eq("id", recommendation_id).execute()

        return plan

    except Exception as e:
        return {"error": f"Plan generation failed: {e}"}


def _generate_steps(title: str, description: str, module: str) -> list[dict]:
    """Generate implementation steps based on recommendation content."""
    steps = []
    text = (title + " " + description).lower()

    # Detect affected areas and generate appropriate steps
    if any(kw in text for kw in ["s05", "discovery", "klip keşfi", "clip discovery"]):
        steps.append({
            "order": 1,
            "file": FILE_MAP["s05"],
            "action": "S05 prompt veya discovery logic'ini analiz et, sorunlu kısmı tespit et",
            "risk": "low",
        })
        steps.append({
            "order": 2,
            "file": FILE_MAP["prompts"],
            "action": "Prompt Lab'da yeni prompt varyantı oluştur",
            "risk": "low",
        })
        steps.append({
            "order": 3,
            "action": "create_test_pipeline ile mevcut vs yeni prompt'u test et",
            "risk": "low",
        })

    elif any(kw in text for kw in ["s06", "evaluation", "değerlendirme", "quality gate"]):
        steps.append({
            "order": 1,
            "file": FILE_MAP["s06"],
            "action": "S06 evaluation criteria ve scoring logic'ini incele",
            "risk": "low",
        })
        steps.append({
            "order": 2,
            "action": "Prompt Lab'da scoring criteria varyantı oluştur",
            "risk": "low",
        })
        steps.append({
            "order": 3,
            "action": "A/B test ile eski vs yeni değerlendirme kriterini karşılaştır",
            "risk": "medium",
        })

    elif any(kw in text for kw in ["dna", "channel", "kanal"]):
        steps.append({
            "order": 1,
            "action": "audit_channel_dna ile mevcut DNA sağlığını kontrol et",
            "risk": "low",
        })
        steps.append({
            "order": 2,
            "action": "Son başarılı klipleri analiz edip DNA güncellemesi öner",
            "risk": "low",
        })
        steps.append({
            "order": 3,
            "action": "update_channel_dna ile değişiklikleri uygula",
            "risk": "medium",
        })
        steps.append({
            "order": 4,
            "action": "create_test_pipeline ile yeni DNA'yı test et",
            "risk": "low",
        })

    elif any(kw in text for kw in ["maliyet", "cost", "token", "expensive"]):
        steps.append({
            "order": 1,
            "action": "get_cost_breakdown ile adım bazlı maliyet analizi yap",
            "risk": "low",
        })
        steps.append({
            "order": 2,
            "action": "En pahalı adımı tespit et (genellikle S05 video input)",
            "risk": "low",
        })
        steps.append({
            "order": 3,
            "action": "Flash pre-screening veya video trim stratejisi değerlendir",
            "risk": "medium",
        })

    elif any(kw in text for kw in ["performans", "performance", "pass rate", "düşüş", "drop"]):
        steps.append({
            "order": 1,
            "action": "get_pass_rate_trend ile trend detayını incele",
            "risk": "low",
        })
        steps.append({
            "order": 2,
            "action": "Content type bazında kırılım analizi yap",
            "risk": "low",
        })
        steps.append({
            "order": 3,
            "action": "Düşen content type'lar için S05/S06 loglarını incele",
            "risk": "low",
        })
        steps.append({
            "order": 4,
            "action": "Channel DNA veya prompt değişikliği öner ve test et",
            "risk": "medium",
        })

    # Default fallback
    if not steps:
        steps = [
            {"order": 1, "action": "İlgili modülü ve logları incele", "risk": "low"},
            {"order": 2, "action": "Root cause analizi yap", "risk": "low"},
            {"order": 3, "action": "Çözüm öner ve test pipeline ile doğrula", "risk": "medium"},
            {"order": 4, "file": "docs/", "action": "Değişiklikleri dokümante et", "risk": "low"},
        ]

    # Always add documentation step
    if not any("dokümante" in s.get("action", "") for s in steps):
        steps.append({
            "order": len(steps) + 1,
            "action": "Sonuçları director memory'ye kaydet",
            "risk": "low",
        })

    return steps


def _assess_total_risk(steps: list[dict]) -> str:
    """Assess overall plan risk from individual step risks."""
    risks = [s.get("risk", "low") for s in steps]
    if "high" in risks:
        return "high"
    if risks.count("medium") >= 2:
        return "medium"
    if "medium" in risks:
        return "low-medium"
    return "low"


def _estimate_impact(title: str, description: str, priority: int) -> str:
    """Estimate expected impact based on recommendation priority and content."""
    text = (title + " " + description).lower()

    if priority <= 1:
        base = "Yüksek etki"
    elif priority <= 2:
        base = "Orta-yüksek etki"
    elif priority <= 3:
        base = "Orta etki"
    else:
        base = "Düşük etki"

    if any(kw in text for kw in ["pass rate", "performans"]):
        return f"{base} — pass rate'de +5-15pp iyileşme beklenir"
    elif any(kw in text for kw in ["maliyet", "cost"]):
        return f"{base} — %20-40 maliyet tasarrufu beklenir"
    elif any(kw in text for kw in ["dna", "channel"]):
        return f"{base} — klip kalitesinde tutarlılık artışı beklenir"
    return base


def _check_prerequisites(steps: list[dict]) -> list[str]:
    """Check if any prerequisites are needed before executing the plan."""
    prereqs = []
    for s in steps:
        action = s.get("action", "").lower()
        if "test_pipeline" in action or "test et" in action:
            prereqs.append("Migration 006 (is_test_run) uygulanmış olmalı")
            break
    for s in steps:
        action = s.get("action", "").lower()
        if "a/b test" in action:
            prereqs.append("Günlük A/B test limiti (2) kontrol edilmeli")
            break
    return list(set(prereqs))
