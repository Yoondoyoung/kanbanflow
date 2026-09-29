"""Ticket attachment storage and image handling.

Files live on disk under ATTACHMENTS_DIR, named by ids this app generates, so an uploaded
filename never reaches the filesystem. path/save/delete are the only code that touches the
directory; swap them to move storage to S3.
"""

import io
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from app.config import settings

ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
PROJECT_QUOTA_BYTES = 1024 * 1024 * 1024
IMAGE_MAX_EDGE = 2000
# ponytail: a decode at the cap is ~100 MB of RGBA on a 512 MB nano, and two concurrent
# uploads double it. Put a semaphore around prepare() if uploads become concurrent.
IMAGE_MAX_PIXELS = 25_000_000
FILENAME_MAX_LENGTH = 255
CONTENT_TYPE_MAX_LENGTH = 100
OCTET_STREAM = "application/octet-stream"


def path(project_id: str, attachment_id: str) -> Path:
    return Path(settings.attachments_dir) / project_id / attachment_id


def save(project_id: str, attachment_id: str, data: bytes) -> None:
    target = path(project_id, attachment_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def delete(project_id: str, attachment_id: str) -> None:
    path(project_id, attachment_id).unlink(missing_ok=True)


def delete_project_files(project_id: str) -> None:
    shutil.rmtree(Path(settings.attachments_dir) / project_id, ignore_errors=True)


def clean_filename(filename: str | None) -> str:
    name = re.split(r"[\\/]", filename or "")[-1]
    name = "".join(char if char.isprintable() else " " for char in name)
    return " ".join(name.split())[:FILENAME_MAX_LENGTH] or "file"


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _reencode(data: bytes) -> bytes | None:
    """Downscale to IMAGE_MAX_EDGE and drop metadata. None means keep the original bytes."""
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > IMAGE_MAX_PIXELS:
            raise ValueError("image is too large to decode safely")
        if getattr(image, "is_animated", False):
            return None  # resizing keeps only the first frame
        image_format = image.format
        icc_profile = image.info.get("icc_profile")  # keeps wide-gamut phone photos' colors
        image.draft(image.mode, (IMAGE_MAX_EDGE, IMAGE_MAX_EDGE))  # JPEG: decode at reduced scale
        image = ImageOps.exif_transpose(image)
        if image.mode == "P" and max(image.size) > IMAGE_MAX_EDGE:
            image = image.convert("RGBA")  # palette images resize with nearest-neighbour
        image.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE))
        options = {"optimize": True} if image_format == "PNG" else {"quality": 85}
        out = io.BytesIO()
        image.save(out, image_format, icc_profile=icc_profile, **options)  # no exif= drops EXIF
        return out.getvalue()


def prepare(data: bytes, declared_type: str | None) -> tuple[bytes, str, bool]:
    """Return (bytes to store, content type, is_image) for one incoming file."""
    image_type = sniff_image(data)
    if image_type is None:
        return data, (declared_type or OCTET_STREAM)[:CONTENT_TYPE_MAX_LENGTH], False
    if image_type == "image/gif":
        return data, image_type, True  # resizing would drop the animation
    try:
        stored = _reencode(data)
    except Exception:  # corrupt, truncated, or over the pixel cap: keep it as a download
        return data, OCTET_STREAM, False
    return (data if stored is None else stored), image_type, True
