import os
import json
from pathlib import Path
from dotenv import load_dotenv
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai


load_dotenv(Path(__file__).parent.parent / ".env")


class Youtube:
    """YouTube service for fetching videos and extracting job openings."""

    def __init__(self):
        self.api_key = os.getenv("GCP_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = "gemini-2.5-flash"

        if not self.api_key:
            raise ValueError("GCP_API_KEY not found")
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not found")

        self.youtube = build("youtube", "v3", developerKey=self.api_key)
        genai.configure(api_key=self.gemini_api_key)
        self.gemini = genai.GenerativeModel(self.gemini_model)

    def get_recent_videos(
        self,
        channel_id: str,
        max_results: int = 5,
        published_after: str | None = None
    ) -> list:

        params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": max_results,
            "type": "video"
        }

        if published_after:
            params["publishedAfter"] = published_after

        request = self.youtube.search().list(**params)
        response = request.execute()

        videos = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": snippet["title"],
                "description": snippet["description"],
                "publishedAt": snippet["publishedAt"]
            })

        return videos

    def get_transcript(self, video_id: str) -> str:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(item["text"] for item in transcript)
        except Exception:
            return ""

    def get_title_description(self, video_id: str) -> dict:
        request = self.youtube.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()

        if not response.get("items"):
            return {"title": "", "description": ""}

        snippet = response["items"][0]["snippet"]
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", "")
        }

    def extract_jobs_with_gemini(self, title: str, description: str, transcript: str) -> dict:
        prompt = f"""
IMPORTANT:
- Respond with STRICT VALID JSON only.
- No markdown.
- No explanations.
- No trailing commas.

You are an AI assistant that extracts job and internship openings from YouTube videos.

Video Title:
{title}

Video Description:
{description}

Video Transcript:
{transcript}

Your Tasks:
1. Determine whether this video contains one or more genuine job or internship openings.
2. If multiple openings are mentioned, extract EACH opening separately.
3. Ignore promotions, sponsorships, personal mentoring, WhatsApp channels, referrals, discounts, and unrelated links.
4. Prefer official application links.
5. Normalize and correct company names if misspelled.
6. If workMode is "Remote", set location to "WFH".

Return STRICT JSON ONLY:

{{
  "isJobVideo": boolean,
  "openings": [
    {{
      "company": string | null,
      "role": string | null,
      "employmentType": "Internship" | "Full-time" | "Contract" | null,
      "workMode": "On-site" | "Remote" | "Hybrid" | null,
      "duration": string | null,
      "location": string | null,
      "requiredSkills": [string],
      "applyLink": string | null,
      "summary": string
    }}
  ]
}}
"""
        response = self.gemini.generate_content(prompt)
        return json.loads(response.text)

    def process_video_for_jobs(self, video_id: str) -> dict:
        transcript = self.get_transcript(video_id)
        if not transcript:
            return {"isJobVideo": False, "openings": []}

        meta = self.get_title_description(video_id)
        return self.extract_jobs_with_gemini(
            meta["title"],
            meta["description"],
            transcript
        )

    def process_channel(self, channel_id: str, max_results: int = 5) -> list:
        results = []
        videos = self.get_recent_videos(channel_id, max_results)

        for video in videos:
            data = self.process_video_for_jobs(video["videoId"])
            if data.get("isJobVideo"):
                results.append({
                    "videoId": video["videoId"],
                    "openings": data["openings"]
                })

        return results
