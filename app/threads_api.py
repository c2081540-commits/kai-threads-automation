from .settings import settings

class ThreadsAPI:
    def __init__(self):
        import requests

        if not settings.threads_user_id or not settings.threads_access_token:
            raise RuntimeError("Threads API認証情報が未設定です")
        self.base = f"https://graph.threads.net/{settings.threads_api_version}"
        self.user_id = settings.threads_user_id
        self.token = settings.threads_access_token
        self.session = requests.Session()

    def _post(self, path, data):
        # 投稿POSTは自動再試行しない。タイムアウト後に再送すると
        # Threads側では成功していて二重投稿になる可能性があるため。
        response = self.session.post(
            f"{self.base}/{path}",
            data=data,
            timeout=(5, 25),
        )
        if not response.ok:
            raise RuntimeError(
                f"Threads API POST {path} failed: "
                f"HTTP {response.status_code} body={response.text[:2000]}"
            )
        return response.json()

    def _get(self, path, params):
        # GETも呼び出し元で回数を管理し、HTTP層では自動再試行しない。
        response = self.session.get(
            f"{self.base}/{path}",
            params=params,
            timeout=(5, 20),
        )
        if not response.ok:
            raise RuntimeError(
                f"Threads API GET {path} failed: "
                f"HTTP {response.status_code} body={response.text[:2000]}"
            )
        return response.json()

    def _wait_until_ready(self, creation_id, attempts=20, interval=3):
        import time

        for attempt in range(attempts):
            result = self._get(
                creation_id,
                {
                    "fields": "status,error_message",
                    "access_token": self.token,
                },
            )
            status = str(result.get("status") or "").upper()
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(
                    f"Threads image container {creation_id} failed: "
                    f"status={status}, "
                    f"error_message={result.get('error_message', '')}"
                )
            if attempt < attempts - 1:
                time.sleep(interval)

        raise RuntimeError(
            f"Threads image container {creation_id} was not ready "
            f"after {attempts * interval} seconds"
        )

    def verify_identity(self):
        result = self._get(
            "me",
            {
                "fields": "id,username",
                "access_token": self.token,
            },
        )
        if str(result.get("id")) != str(self.user_id):
            raise RuntimeError(
                "THREADS_USER_IDとアクセストークンの利用者が一致しません"
            )
        return {
            "id": str(result["id"]),
            "username": result.get("username", ""),
        }

    def publish_text(self, text, reply_to_id=None):
        common = {"access_token": self.token}
        payload = {**common, "media_type": "TEXT", "text": text}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        container = self._post(
            f"{self.user_id}/threads",
            payload,
        )
        published = self._post(
            f"{self.user_id}/threads_publish",
            {**common, "creation_id": container["id"]},
        )
        return published["id"]

    def publish_image(self, text, image_url, reply_to_id=None):
        common = {"access_token": self.token}
        payload = {
            **common,
            "media_type": "IMAGE",
            "image_url": image_url,
            "text": text,
        }
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        container = self._post(
            f"{self.user_id}/threads",
            payload,
        )
        self._wait_until_ready(container["id"])
        published = self._post(
            f"{self.user_id}/threads_publish",
            {**common, "creation_id": container["id"]},
        )
        return published["id"]

    def media(self, media_id):
        return self._get(
            media_id,
            {"fields": "id,permalink,timestamp,text", "access_token": self.token},
        )

    def insights(self, media_id):
        metrics = "views,likes,replies,reposts,quotes,shares"
        return self._get(
            f"{media_id}/insights",
            {"metric": metrics, "access_token": self.token},
        )
