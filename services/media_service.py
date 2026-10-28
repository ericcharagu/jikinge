import uuid

import aiofiles
import httpx

from config import WHATSAPP_HEADERS, WHATSAPP_MEDIA_URL
from domain.excepts import MediaDownloadException


class MediaService:
    def __init__(self) -> None:
        self.url: str = WHATSAPP_MEDIA_URL
        self.headers: dict[str, str] = WHATSAPP_HEADERS

    async def download_whatsapp_media(self, media_id: str) -> str:
        try:
            url = f"{self.url}/{media_id}"

            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=self.headers)
                res.raise_for_status()
                media_url = res.json().get("url")

                media_res = await client.get(media_url, headers=self.headers)
                media_res.raise_for_status()

                ext = media_res.headers.get("content-type", "image/jpeg").split("/")[-1]
                path = f"media_files/{uuid.uuid4()}.{ext}"

                async with aiofiles.open(path, mode="wb") as f:
                    await f.write(media_res.content)
            return path
        except Exception as e:
            raise MediaDownloadException(media_id, e) from e
