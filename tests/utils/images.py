from io import BytesIO

from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()


def make_test_image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format=image_format)
    return output.getvalue()


def make_exif_test_jpeg_bytes() -> bytes:
    output = BytesIO()
    exif = Image.Exif()
    exif[315] = "Crane Spotter Test"
    Image.new("RGB", (2, 2), color="white").save(
        output,
        format="JPEG",
        exif=exif,
    )
    return output.getvalue()


TEST_JPEG_BYTES = make_test_image_bytes("JPEG")
TEST_PNG_BYTES = make_test_image_bytes("PNG")
TEST_GIF_BYTES = make_test_image_bytes("GIF")
TEST_HEIF_BYTES = make_test_image_bytes("HEIF")
TEST_EXIF_JPEG_BYTES = make_exif_test_jpeg_bytes()
