import unittest
from io import BytesIO
from PIL import Image
from image_ops import compress, make_capture, selection_box


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.effect_noise((420, 300), 90).convert("RGBA")

    def test_reverse_and_bounded_square(self):
        self.assertEqual(selection_box((100, 100), (-10, 50), (300, 300), True),
                         (50, 50, 100, 100))

    def test_circle_mask_and_dimensions(self):
        result = make_capture(self.image, (0, 0, 200, 200), "circle", (80, 80))
        self.assertEqual(result.size, (80, 80))
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((40, 40))[3], 255)

    def test_target_all_formats(self):
        for fmt in ("JPEG", "WEBP", "PNG"):
            with self.subTest(fmt=fmt):
                data, size, _ = compress(self.image, 6 * 1024, fmt)
                self.assertLessEqual(len(data), 6 * 1024)
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    self.assertEqual(image.size, size)
                    self.assertEqual(image.format, fmt)

    def test_impossible_without_resize(self):
        with self.assertRaises(ValueError):
            compress(self.image, 1024, "PNG", False)

    def test_cancel(self):
        with self.assertRaises(InterruptedError):
            compress(self.image, 2048, cancelled=lambda: True)

    def test_webp_transparency(self):
        image = make_capture(self.image, (0, 0, 200, 200), "circle")
        data, _, _ = compress(image, 100 * 1024)
        with Image.open(BytesIO(data)) as decoded:
            self.assertEqual(decoded.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            compress(self.image, 0)


if __name__ == "__main__":
    unittest.main()
