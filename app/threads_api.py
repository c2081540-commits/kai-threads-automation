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
        response.raise_for_status()
        return response.json()

    def _get(self, path, params):
        # GETも呼び出し元で回数を管理し、HTTP層では自動再試行しない。
        response = self.session.get(
            f"{self.base}/{path}",
            params=params,
            timeout=(5, 20),
        )
        response.raise_for_status()
        return response.json()

    def publish_text(self, text):
        common = {"access_token": self.token}
        container = self._post(
            f"{self.user_id}/threads",
            {**common, "media_type": "TEXT", "text": text},
        )
        published = self._post(
            f"{self.user_id}/threads_publish",
            {**common, "creation_id": container["id"]},
        )
        return published["id"]

    def publish_image(self, text, image_url):
        common = {"access_token": self.token}
        container = self._post(
            f"{self.user_id}/threads",
            {
                **common,
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": text,
            },
        )
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
