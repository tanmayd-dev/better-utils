"""Media tools: file uploads and image artifacts."""

import hashlib

from PIL import Image

from better_utils import File, ImageFile, Router

media = Router("media")


@media.tool(name="Thumbnail")
def thumbnail(img: ImageFile, width: int = 128) -> Image.Image:
    """Generates a grayscale thumbnail from the uploaded image."""
    if width < 8:
        from better_utils import ToolError

        raise ToolError("width must be at least 8 pixels")
    scale = width / img.width
    target = Image.new("RGB", (width, max(1, int(img.height * scale))))
    target.paste(img.resize((width, max(1, int(img.height * scale)))), (0, 0))
    return target.convert("L")


@media.tool(name="Checksum")
def sha256_checksum(file: File) -> dict:
    """Hashes an uploaded file with SHA-256."""
    digest = hashlib.sha256(file).hexdigest()
    return {"sha256": digest, "bytes": len(file)}
