"""Hardened resume-portrait decoding and metadata-free normalization."""

from __future__ import annotations

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_RESUME_PHOTO_BYTES = 5 * 1024 * 1024
MAX_RESUME_PHOTO_DIMENSION = 6000
MAX_RESUME_PHOTO_PIXELS = 20_000_000
_MEDIA_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


class UnsafeImageError(ValueError):
    """Raised when an uploaded portrait is not safe to decode and normalize."""


def _validate_geometry(image: Image.Image) -> None:
    width, height = image.size
    if width < 1 or height < 1:
        raise UnsafeImageError("Image dimensions are invalid")
    if width > MAX_RESUME_PHOTO_DIMENSION or height > MAX_RESUME_PHOTO_DIMENSION:
        raise UnsafeImageError("Image dimensions exceed the allowed maximum")
    if width * height > MAX_RESUME_PHOTO_PIXELS:
        raise UnsafeImageError("Image pixel count exceeds the allowed maximum")
    if int(getattr(image, "n_frames", 1)) != 1:
        raise UnsafeImageError("Animated or multi-frame images are not supported")


def normalize_resume_photo(media_type: str, image_bytes: bytes) -> tuple[str, bytes]:
    """Fully decode, validate, orient, strip metadata, and re-encode a portrait."""
    expected_format = _MEDIA_FORMATS.get(media_type)
    if expected_format is None:
        raise UnsafeImageError("Unsupported image media type")
    if not image_bytes or len(image_bytes) > MAX_RESUME_PHOTO_BYTES:
        raise UnsafeImageError("Image byte size is outside the allowed range")

    previous_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_RESUME_PHOTO_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                BytesIO(image_bytes),
                formats=list(_MEDIA_FORMATS.values()),
            ) as probe:
                if probe.format != expected_format:
                    raise UnsafeImageError("Image content does not match its media type")
                _validate_geometry(probe)
                probe.verify()

            with Image.open(
                BytesIO(image_bytes),
                formats=[expected_format],
            ) as decoded:
                _validate_geometry(decoded)
                normalized = ImageOps.exif_transpose(decoded)
                normalized.load()
                _validate_geometry(normalized)
                if expected_format == "JPEG":
                    normalized = normalized.convert("RGB")
                elif expected_format == "PNG":
                    normalized = normalized.convert(
                        "RGBA" if "A" in normalized.getbands() else "RGB"
                    )
                else:
                    normalized = normalized.convert(
                        "RGBA" if "A" in normalized.getbands() else "RGB"
                    )
                output = BytesIO()
                if expected_format == "JPEG":
                    normalized.save(
                        output,
                        format="JPEG",
                        quality=90,
                        optimize=True,
                        progressive=True,
                    )
                elif expected_format == "PNG":
                    normalized.save(output, format="PNG", optimize=True)
                else:
                    normalized.save(output, format="WEBP", quality=90, method=6)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        if isinstance(error, UnsafeImageError):
            raise
        raise UnsafeImageError("Image decoding or validation failed") from error
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_pixels

    normalized_bytes = output.getvalue()
    if not normalized_bytes or len(normalized_bytes) > MAX_RESUME_PHOTO_BYTES:
        raise UnsafeImageError("Normalized image exceeds the allowed byte size")
    return media_type, normalized_bytes
