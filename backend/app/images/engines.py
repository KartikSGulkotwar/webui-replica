"""Image engines: each turns a prompt into one image (bytes + media type)."""

import asyncio
import base64
import binascii
from dataclasses import dataclass
from urllib.parse import quote

import httpx

ENGINES = {
    "pollinations": "Pollinations (free, no key)",
    "openai": "OpenAI-compatible",
    "automatic1111": "Automatic1111 / Stable Diffusion WebUI",
}
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"
SIZES = ("512x512", "768x768", "1024x1024", "1024x1536", "1536x1024")
MAX_BYTES = 4_000_000  # also keeps responses under Vercel's 4.5 MB limit
TIMEOUT = httpx.Timeout(120.0, connect=10.0)  # images take a while
# Anonymous use allows one image per ~15 s per address, and a refused request
# starts the wait over, so each retry waits the full interval.
POLLINATIONS_RETRY_PAUSES = (16.0, 16.0)  # seconds


class ImageError(Exception):
    pass


@dataclass(frozen=True)
class ImageConfig:
    engine: str  # "" = off
    base_url: str = ""
    api_key: str | None = None
    model: str = ""
    size: str = "1024x1024"

    @property
    def enabled(self) -> bool:
        if self.engine == "pollinations":
            return True
        if self.engine == "automatic1111":
            return bool(self.base_url)
        if self.engine == "openai":
            return bool(self.base_url and self.model)
        return False

    @property
    def dimensions(self) -> tuple[int, int]:
        width, _, height = self.size.partition("x")
        return int(width), int(height)


@dataclass(frozen=True)
class Image:
    data: bytes
    mime: str


def _sniff(data: bytes) -> str:
    """Media type from the file's first bytes (engines don't always say)."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ImageError("The image engine didn't return an image")


def _checked(data: bytes) -> Image:
    if len(data) > MAX_BYTES:
        raise ImageError("The image is too large to keep (over 4 MB); try a smaller size")
    return Image(data, _sniff(data))


def _decode(b64: str) -> Image:
    try:
        return _checked(base64.b64decode(b64, validate=False))
    except (binascii.Error, ValueError) as exc:
        raise ImageError("The image engine returned an unreadable image") from exc


def _error(resp: httpx.Response, engine: str) -> ImageError:
    if resp.status_code in (401, 403):
        return ImageError(f"{engine} rejected the API key")
    if resp.status_code == 429:
        return ImageError(f"{engine} rate limit reached; try again later")
    detail = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        detail = (err.get("message") if isinstance(err, dict) else err) or body.get("detail") or ""
    except ValueError:
        pass
    if "safety" in str(detail).lower() or "content_policy" in str(detail).lower():
        return ImageError(f"{engine} declined this prompt: {str(detail)[:200]}")
    return ImageError(f"{engine} returned HTTP {resp.status_code} {str(detail)[:200]}".strip())


async def generate(http: httpx.AsyncClient, config: ImageConfig, prompt: str) -> Image:
    prompt = prompt.strip()[:4000]
    if not config.enabled:
        raise ImageError("Image generation isn't set up")
    if not prompt:
        raise ImageError("The image prompt is empty")
    width, height = config.dimensions
    try:
        if config.engine == "pollinations":
            url = f"{POLLINATIONS_URL}/{quote(prompt, safe='')}"
            params = {
                "width": width,
                "height": height,
                "nologo": "true",
                **({"model": config.model} if config.model else {}),
            }
            # The free tier allows one image every few seconds per address and
            # answers 402/429 in between: wait and try again.
            for pause in (*POLLINATIONS_RETRY_PAUSES, None):
                resp = await http.get(url, params=params, timeout=TIMEOUT, follow_redirects=True)
                if resp.status_code not in (402, 429) or pause is None:
                    break
                await asyncio.sleep(pause)
            if resp.status_code in (402, 429):
                raise ImageError("Pollinations' free tier is busy; try again in a few seconds")
            if resp.status_code >= 400:
                raise _error(resp, "Pollinations")
            return _checked(resp.content)

        if config.engine == "automatic1111":
            resp = await http.post(
                f"{config.base_url}/sdapi/v1/txt2img",
                json={"prompt": prompt, "width": width, "height": height, "steps": 25},
                # Its --api-auth login, entered as "user:password".
                auth=tuple(config.api_key.split(":", 1)) if config.api_key else None,  # type: ignore[arg-type]
                timeout=TIMEOUT,
            )
            if resp.status_code >= 400:
                raise _error(resp, "Automatic1111")
            images = resp.json().get("images") or []
            if not images:
                raise ImageError("Automatic1111 returned no image")
            return _decode(images[0])

        # OpenAI-compatible /images/generations
        body: dict = {"model": config.model, "prompt": prompt, "n": 1, "size": config.size}
        # DALL·E returns links by default; gpt-image models always return base64.
        if config.model.startswith("dall-e"):
            body["response_format"] = "b64_json"
        resp = await http.post(
            f"{config.base_url}/images/generations",
            json=body,
            headers={"Authorization": f"Bearer {config.api_key}"} if config.api_key else {},
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            raise _error(resp, "The image API")
        data = (resp.json().get("data") or [{}])[0]
        if data.get("b64_json"):
            return _decode(data["b64_json"])
        if data.get("url"):
            got = await http.get(data["url"], timeout=TIMEOUT)
            if got.status_code >= 400:
                raise ImageError("Couldn't download the generated image")
            return _checked(got.content)
        raise ImageError("The image API returned no image")
    except httpx.TimeoutException as exc:
        raise ImageError("The image engine took too long to respond") from exc
    except httpx.HTTPError as exc:
        raise ImageError(f"Couldn't reach the image engine: {exc.__class__.__name__}") from exc
    except ValueError as exc:  # JSON
        raise ImageError("The image engine returned something unexpected") from exc
