"""Parameter marshallers.

These classes are sentinels used *as annotations* in tool signatures. The
schema parser recognizes them and marks the argument accordingly:

    def flatten_pdf(source: File, image: ImageFile) -> bytes: ...

``File`` keeps the raw uploaded bytes; ``ImageFile`` opens the upload with
Pillow before the tool runs.
"""

from __future__ import annotations

__all__ = ["File", "ImageFile"]


class File:
    """Marks a parameter as an uploaded file.

    The tool receives the raw ``bytes`` of the upload.
    """

    accept: str = "*/*"


class ImageFile:
    """Marks a parameter as an uploaded image.

    The tool receives a :class:`PIL.Image.Image`.
    """

    accept: str = "image/*"


def is_file_type(annotation: object) -> bool:
    """Return True when ``annotation`` is one of the file sentinels."""
    if annotation is File or annotation is ImageFile:
        return True
    if isinstance(annotation, type):
        try:
            return issubclass(annotation, (File, ImageFile))
        except TypeError:
            return False
    return False
