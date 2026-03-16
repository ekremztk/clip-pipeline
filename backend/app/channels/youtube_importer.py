import os
import subprocess
import requests

from app.services.supabase_client import get_client
from app.config import settings

def get_channel_shorts(youtube_channel_id: str, api_key: str, max_results: int = 50) -> list:
    """
    Fetches up to 3 pages of YouTube Shorts for a given channel.
    """
    shorts_data = []
    base_url = "https://www.googleapis.com/youtube/v3"
    next_page_token: str | None = None
    
    try:
        for _ in range(3):
            search_url = f"{base_url}/search"
            search_params: dict[str, str | int] = {
                "part": "id,snippet",
                "channelId": youtube_channel_id,
                "type": "video",
                "videoDuration": "short",
                "maxResults": max_results,
                "order": "date",
                "key": api_key
            }
            if next_page_token:
                search_params["pageToken"] = next_page_token
                
            search_resp = requests.get(search_url, params=search_params)
            search_resp.raise_for_status()
            search_data = search_resp.json()
            
            items = search_data.get("items", [])
            if not items:
                break
                
            video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
            if not video_ids:
                break
                
            # Now fetch statistics
            videos_url = f"{base_url}/videos"
            videos_params = {
                "part": "statistics,contentDetails,snippet",
                "id": ",".join(video_ids),
                "key": api_key
            }
            
            videos_resp = requests.get(videos_url, params=videos_params)
            videos_resp.raise_for_status()
            videos_data = videos_resp.json()
            
            for item in videos_data.get("items", []):
                vid_id = item["id"]
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                content_details = item.get("contentDetails", {})
                
                shorts_data.append({
                    "video_id": vid_id,
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "view_count": int(statistics.get("viewCount", 0)),
                    "like_count": int(statistics.get("likeCount", 0)),
                    "duration": content_details.get("duration", "")
                })
                
            next_page_token = search_data.get("nextPageToken")
            if not next_page_token:
                break
                
        return shorts_data
    except Exception as e:
        print(f"[YouTubeImporter] Error fetching channel shorts: {e}")
        return []

def calculate_channel_average(shorts: list) -> float:
    """
    Calculate average view_count from shorts list
    """
    try:
        if not shorts:
            return 0.0
        total_views = sum(short.get("view_count", 0) for short in shorts)
        return float(total_views) / len(shorts)
    except Exception as e:
        print(f"[YouTubeImporter] Error calculating average: {e}")
        return 0.0

def identify_successful_shorts(shorts: list, multiplier: float = 1.5) -> list:
    """
    Identify shorts with view_count > channel_average * multiplier
    """
    try:
        if not shorts:
            return []
            
        avg_views = calculate_channel_average(shorts)
        threshold = avg_views * multiplier
        
        successful = [s for s in shorts if s.get("view_count", 0) > threshold]
        successful.sort(key=lambda x: x.get("view_count", 0), reverse=True)
        
        print(f"[YouTubeImporter] {len(successful)} successful out of {len(shorts)} total")
        return successful
    except Exception as e:
        print(f"[YouTubeImporter] Error identifying successful shorts: {e}")
        return []

def download_short(video_id: str, output_dir: str) -> str | None:
    """
    Downloads a short using yt-dlp
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            
        output_path = f"{output_dir}/{video_id}.mp4"
        
        command = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--output", output_path,
            f"https://www.youtube.com/shorts/{video_id}"
        ]
        
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if os.path.exists(output_path):
            return output_path
        else:
            print(f"[YouTubeImporter] Download finished but file not found: {output_path}")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"[YouTubeImporter] yt-dlp error for {video_id}: {e.stderr.decode('utf-8', errors='ignore')}")
        return None
    except Exception as e:
        print(f"[YouTubeImporter] Error downloading short {video_id}: {e}")
        return None
