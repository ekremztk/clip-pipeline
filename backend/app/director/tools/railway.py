"""Director Railway tool — deployment status, resource metrics, logs."""

import os
import json
import urllib.request
import urllib.error
from app.config import settings

RAILWAY_API_URL = "https://backboard.railway.app/graphql/v2"


def _gql(query: str, variables: dict | None = None) -> dict:
    token = os.getenv("RAILWAY_API_TOKEN", "")
    if not token:
        raise ValueError("RAILWAY_API_TOKEN not set")

    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        RAILWAY_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_railway_status() -> dict:
    """
    Fetch Railway project status: services, latest deployments, health.
    Returns deployment statuses, latest build info, and service details.
    """
    try:
        project_id = os.getenv("RAILWAY_PROJECT_ID", "")

        if project_id:
            query = """
            query($projectId: String!) {
              project(id: $projectId) {
                id
                name
                services {
                  edges {
                    node {
                      id
                      name
                      deployments(last: 3) {
                        edges {
                          node {
                            id
                            status
                            createdAt
                            meta
                            url
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            data = _gql(query, {"projectId": project_id})
            project = data.get("data", {}).get("project", {})
        else:
            # Fallback: fetch all projects
            query = """
            query {
              me {
                projects {
                  edges {
                    node {
                      id
                      name
                      services {
                        edges {
                          node {
                            id
                            name
                            deployments(last: 2) {
                              edges {
                                node {
                                  id
                                  status
                                  createdAt
                                  url
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            data = _gql(query)
            projects = [
                e["node"] for e in
                data.get("data", {}).get("me", {}).get("projects", {}).get("edges", [])
            ]
            # Return all projects summary
            result = []
            for p in projects:
                services = []
                for se in p.get("services", {}).get("edges", []):
                    svc = se["node"]
                    deployments = [
                        {
                            "id": de["node"]["id"],
                            "status": de["node"]["status"],
                            "createdAt": de["node"].get("createdAt"),
                            "url": de["node"].get("url"),
                        }
                        for de in svc.get("deployments", {}).get("edges", [])
                    ]
                    services.append({
                        "name": svc["name"],
                        "latest_deployment": deployments[0] if deployments else None,
                    })
                result.append({"project": p["name"], "services": services})
            return {"projects": result}

        # Format single project result
        services = []
        for se in project.get("services", {}).get("edges", []):
            svc = se["node"]
            deployments = [
                {
                    "id": de["node"]["id"],
                    "status": de["node"]["status"],
                    "createdAt": de["node"].get("createdAt"),
                    "url": de["node"].get("url"),
                }
                for de in svc.get("deployments", {}).get("edges", [])
            ]
            services.append({
                "name": svc["name"],
                "latest_deployment": deployments[0] if deployments else None,
                "recent_deployments": deployments,
            })

        return {
            "project": project.get("name"),
            "project_id": project.get("id"),
            "services": services,
        }

    except ValueError as e:
        return {"error": str(e), "hint": "Add RAILWAY_API_TOKEN to Railway env vars"}
    except Exception as e:
        print(f"[DirectorRailway] error: {e}")
        return {"error": str(e)}


def get_railway_logs(service_name: str | None = None, limit: int = 50) -> dict:
    """
    Fetch recent deployment logs from Railway.
    Requires RAILWAY_API_TOKEN. RAILWAY_PROJECT_ID optional (uses first project if not set).
    """
    try:
        # First get deployment ID for the service (works with or without RAILWAY_PROJECT_ID)
        status = get_railway_status()
        if "error" in status:
            return status

        deployment_id = None
        for svc in status.get("services", []):
            if service_name is None or service_name.lower() in svc["name"].lower():
                dep = svc.get("latest_deployment")
                if dep:
                    deployment_id = dep["id"]
                    break

        if not deployment_id:
            return {"error": f"No active deployment found for service: {service_name}"}

        query = """
        query($deploymentId: String!, $limit: Int!) {
          deploymentLogs(deploymentId: $deploymentId, limit: $limit) {
            timestamp
            message
            severity
          }
        }
        """
        data = _gql(query, {"deploymentId": deployment_id, "limit": limit})
        logs = data.get("data", {}).get("deploymentLogs", [])
        return {
            "deployment_id": deployment_id,
            "log_count": len(logs),
            "logs": logs,
        }

    except Exception as e:
        print(f"[DirectorRailway] get_railway_logs error: {e}")
        return {"error": str(e)}
