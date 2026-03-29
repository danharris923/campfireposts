#!/usr/bin/env python3
"""
Metricool API wrapper for scheduling Campfire Kitchen image posts.
Uses Supabase storage for public image hosting.
"""

import os
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

METRICOOL_BASE_URL = "https://app.metricool.com"
SUPABASE_BUCKET = "campfire-cards"


def upload_to_supabase(image_path: str) -> str | None:
    """Upload a local image to Supabase Storage, return public URL."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("ERROR: Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return None

    path = Path(image_path)
    remote_name = path.name

    try:
        with open(path, "rb") as f:
            file_data = f.read()

        resp = requests.post(
            f"{url}/storage/v1/object/{SUPABASE_BUCKET}/{remote_name}",
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "image/png",
                "x-upsert": "true",
            },
            data=file_data,
            timeout=30,
        )

        if resp.status_code in [200, 201]:
            public_url = f"{url}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_name}"
            print(f"  Uploaded to Supabase: {remote_name}")
            return public_url

        print(f"  Supabase upload failed: {resp.status_code} {resp.text[:150]}")
        return None
    except Exception as e:
        print(f"  Supabase upload error: {e}")
        return None


class MetricoolAPI:
    def __init__(self):
        self.api_token = os.getenv("METRICOOL_API_TOKEN")
        self.user_id = os.getenv("METRICOOL_USER_ID")
        self.blog_id = os.getenv("METRICOOL_BLOG_ID")
        self.timezone = "America/Vancouver"

        self.session = requests.Session()
        if self.api_token:
            self.session.headers.update({
                "X-Mc-Auth": self.api_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            })

    def _check_config(self) -> bool:
        if not all([self.api_token, self.user_id, self.blog_id]):
            print("ERROR: Missing METRICOOL_API_TOKEN, METRICOOL_USER_ID, or METRICOOL_BLOG_ID in .env")
            return False
        return True

    def normalize_image(self, image_url: str) -> str | None:
        """Normalize a public image URL through Metricool's CDN."""
        try:
            resp = requests.get(
                f"{METRICOOL_BASE_URL}/api/actions/normalize/image/url",
                headers={"X-Mc-Auth": self.api_token},
                params={"url": image_url},
                timeout=30,
            )
            if resp.status_code == 200:
                media_url = resp.text.strip()
                if media_url.startswith("http"):
                    print(f"  Normalized: {media_url[:60]}...")
                    return media_url
            print(f"  Normalize failed: {resp.status_code} {resp.text[:100]}")
            return None
        except Exception as e:
            print(f"  Normalize error: {e}")
            return None

    def schedule_post(
        self,
        caption: str,
        card_path: str,
        post_time: datetime | None = None,
    ) -> dict:
        """Schedule a static PHOTO post to Facebook.
        card_path is a local PNG — uploads to Supabase, normalizes via Metricool, then schedules."""
        if not self._check_config():
            return {"success": False, "error": "Not configured"}

        if post_time is None:
            post_time = datetime.now() + timedelta(minutes=2)

        # Upload card to Supabase for public URL
        print(f"  Uploading card to Supabase...")
        public_url = upload_to_supabase(card_path)
        if not public_url:
            return {"success": False, "error": "Supabase upload failed"}

        # Normalize through Metricool CDN
        print(f"  Normalizing image via Metricool...")
        image_url = self.normalize_image(public_url)
        if not image_url:
            return {"success": False, "error": "Metricool normalize failed"}

        payload = {
            "autoPublish": True,
            "descendants": [],
            "draft": False,
            "firstCommentText": "",
            "hasNotReadNotes": False,
            "media": [image_url],
            "mediaAltText": [],
            "providers": [{"network": "facebook"}],
            "publicationDate": {
                "dateTime": post_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "timezone": self.timezone,
            },
            "shortener": False,
            "smartLinkData": {"ids": []},
            "text": caption,
            "facebookData": {
                "type": "PHOTO",
                "title": "",
            },
        }

        try:
            resp = self.session.post(
                f"{METRICOOL_BASE_URL}/api/v2/scheduler/posts",
                params={"userId": self.user_id, "blogId": self.blog_id},
                json=payload,
                timeout=30,
            )

            if resp.status_code in [200, 201]:
                print(f"  POST SCHEDULED for {post_time.strftime('%Y-%m-%d %H:%M')}")
                return {"success": True, "data": resp.json() if resp.text else {}}

            print(f"  Schedule failed: {resp.status_code} {resp.text[:200]}")
            return {"success": False, "error": resp.text[:200]}

        except Exception as e:
            print(f"  Schedule error: {e}")
            return {"success": False, "error": str(e)}

    def test_connection(self) -> bool:
        """Quick connection test."""
        if not self._check_config():
            return False
        try:
            resp = self.session.get(
                f"{METRICOOL_BASE_URL}/api/admin/simpleProfiles",
                params={"userId": self.user_id},
                timeout=15,
            )
            if resp.status_code == 200:
                profiles = resp.json()
                print(f"  Connected! {len(profiles)} profile(s) found.")
                return True
            print(f"  Connection failed: {resp.status_code}")
            return False
        except Exception as e:
            print(f"  Connection error: {e}")
            return False


if __name__ == "__main__":
    api = MetricoolAPI()
    api.test_connection()
