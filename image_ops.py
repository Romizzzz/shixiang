"""Local image transforms, independent of the desktop UI."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps


def selection_box(start, end, bounds, square=False):
    x0, y0 = start
    x1 = max(0, min(bounds[0], end[0]))
    y1 = max(0, min(bounds[1], end[1]))
    if square:
        side = min(abs(x1 - x0), abs(y1 - y0))
        x1 = x0 + (side if x1 >= x0 else -side)
        y1 = y0 + (side if y1 >= y0 else -side)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def make_capture(image, box, shape, size=None):
    result = image.crop(box).convert("RGBA")
    if size:
        result = result.resize(size, Image.Resampling.LANCZOS)
    if shape in ("circle", "ellipse"):
        # Supersampling keeps the transparent edge smooth.
        w, h = result.size
        mask = Image.new("L", (w * 2, h * 2))
        ImageDraw.Draw(mask).ellipse((0, 0, w * 2 - 1, h * 2 - 1), fill=255)
        result.putalpha(mask.resize((w, h), Image.Resampling.LANCZOS))
    return result


def encode(image, fmt, quality=90):
    out = BytesIO()
    if fmt == "JPEG":
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        background.save(out, format=fmt, quality=quality, optimize=True)
    elif fmt == "WEBP":
        image.save(out, format=fmt, quality=quality, method=4)
    elif fmt == "PNG":
        image.save(out, format=fmt, optimize=True)
    else:
        raise ValueError("Unsupported output format")
    return out.getvalue()


def compress(image, target, fmt="WEBP", allow_resize=True, cancelled=lambda: False):
    if target < 1024:
        raise ValueError("目标大小至少为 1 KB")
    current = ImageOps.exif_transpose(image).convert("RGBA")
    while True:
        if cancelled():
            raise InterruptedError("已取消压缩")
        quality = None
        if fmt == "PNG":
            best = encode(current, fmt)
        else:
            best = None
            low, high = 20, 95
            while low <= high:
                if cancelled():
                    raise InterruptedError("已取消压缩")
                q = (low + high) // 2
                candidate = encode(current, fmt, q)
                if len(candidate) <= target:
                    best, quality, low = candidate, q, q + 1
                else:
                    high = q - 1
        if best is not None and len(best) <= target:
            return best, current.size, quality
        if not allow_resize or current.size == (1, 1):
            raise ValueError("当前尺寸无法达到目标，请允许缩小尺寸或提高大小上限")
        w, h = current.size
        current = current.resize((max(1, int(w * .8)), max(1, int(h * .8))),
                                 Image.Resampling.LANCZOS)
