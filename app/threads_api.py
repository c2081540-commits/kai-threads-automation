import requests
from .settings import settings

class ThreadsAPI:
    def __init__(self):
        if not settings.threads_user_id or not settings.threads_access_token:
            raise RuntimeError("Threads API認証情報が未設定です")
        self.base = f"https://graph.threads.net/{settings.threads_api_version}"
        self.user_id = settings.threads_user_id
        self.token = settings.threads_access_token

    def publish_text(self, text):
        common = {"access_token": self.token}
        c = requests.post(f"{self.base}/{self.user_id}/threads", data={**common,"media_type":"TEXT","text":text}, timeout=30)
        c.raise_for_status()
        container_id = c.json()["id"]
        p = requests.post(f"{self.base}/{self.user_id}/threads_publish", data={**common,"creation_id":container_id}, timeout=30)
        p.raise_for_status()
        return p.json()["id"]

    def publish_image(self, text, image_url):
        common = {"access_token": self.token}
        c = requests.post(
            f"{self.base}/{self.user_id}/threads",
            data={
                **common,
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": text,
            },
            timeout=30,
        )
        c.raise_for_status()
        container_id = c.json()["id"]
        p = requests.post(
            f"{self.base}/{self.user_id}/threads_publish",
            data={**common, "creation_id": container_id},
            timeout=30,
        )
        p.raise_for_status()
        return p.json()["id"]

    def media(self, media_id):
        r = requests.get(f"{self.base}/{media_id}", params={"fields":"id,permalink,timestamp,text","access_token":self.token}, timeout=30)
        r.raise_for_status(); return r.json()

    def insights(self, media_id):
        metrics = "views,likes,replies,reposts,quotes,shares"
        r = requests.get(f"{self.base}/{media_id}/insights", params={"metric":metrics,"access_token":self.token}, timeout=30)
        r.raise_for_status(); return r.json()
