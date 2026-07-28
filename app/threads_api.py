import json
import time

from .settings import settings


class ThreadsAPIError(RuntimeError):
    pass


class ThreadsAPI:
    def __init__(self):
        import requests

        if not settings.threads_user_id or not settings.threads_access_token:
            raise RuntimeError("Threads API認証情報が未設定です")
        self.base = f"https://graph.threads.net/{settings.threads_api_version}"
        self.user_id = settings.threads_user_id
        self.token = settings.threads_access_token
        self.session = requests.Session()

    @staticmethod
    def _safe_body(response):
        try:
            return json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            return response.text[:4000]

    def _raise(self, response, operation):
        if response.ok:
            return
        raise ThreadsAPIError(
            f"Threads API {operation} failed: "
            f"status={response.status_code}, body={self._safe_body(response)}"
        )

    def _post(self, path, data, operation):
        response = self.session.post(
            f"{self.base}/{path}",
            data=data,
            timeout=(5, 25),
        )
        self._raise(response, operation)
        return response.json()

    def _get(self, path, params, operation):
        response = self.session.get(
            f"{self.base}/{path}",
            params=params,
            timeout=(5, 20),
        )
        self._raise(response, operation)
        return response.json()

    def verify_identity(self):
        result = self._get(
            "me",
            {"fields": "id,username", "access_token": self.token},
            "verify_identity",
        )
        if str(result.get("id")) != str(self.user_id):
            raise RuntimeError(
                "THREADS_USER_IDとアクセストークンの利用者が一致しません"
            )
        return {"id": str(result["id"]), "username": result.get("username", "")}

    def _wait_until_ready(self, container_id, operation):
        last = {}
        for _ in range(12):
            last = self._get(
                container_id,
                {
                    "fields": "status,error_message",
                    "access_token": self.token,
                },
                f"{operation}_status",
            )
            status = str(last.get("status", "")).upper()
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise ThreadsAPIError(
                    f"Threads API {operation} container failed: "
                    f"container_id={container_id}, body="
                    f"{json.dumps(last, ensure_ascii=False)}"
                )
            time.sleep(2)
        raise ThreadsAPIError(
            f"Threads API {operation} container timeout: "
            f"container_id={container_id}, body={json.dumps(last, ensure_ascii=False)}"
        )

    def _publish_container(self, container_id, operation):
        self._wait_until_ready(container_id, operation)
        published = self._post(
            f"{self.user_id}/threads_publish",
            {"access_token": self.token, "creation_id": container_id},
            f"{operation}_publish",
        )
        if not published.get("id"):
            raise ThreadsAPIError(
                f"Threads API {operation}_publish returned no id: "
                f"{json.dumps(published, ensure_ascii=False)}"
            )
        return str(published["id"])

    def publish_text(self, text, reply_to_id=None):
        payload = {
            "access_token": self.token,
            "media_type": "TEXT",
            "text": text,
        }
        operation = "reply_text" if reply_to_id else "parent_text"
        if reply_to_id:
            payload["reply_to_id"] = str(reply_to_id)
        container = self._post(
            f"{self.user_id}/threads",
            payload,
            f"{operation}_create",
        )
        return self._publish_container(container["id"], operation)

    def publish_image(self, text, image_url):
        container = self._post(
            f"{self.user_id}/threads",
            {
                "access_token": self.token,
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": text,
            },
            "parent_image_create",
        )
        return self._publish_container(container["id"], "parent_image")

    def media(self, media_id):
        return self._get(
            media_id,
            {"fields": "id,permalink,timestamp,text", "access_token": self.token},
            "media",
        )

    def insights(self, media_id):
        metrics = "views,likes,replies,reposts,quotes,shares"
        return self._get(
            f"{media_id}/insights",
            {"metric": metrics, "access_token": self.token},
            "insights",
        )
