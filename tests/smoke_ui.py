"""Interactive-desktop smoke check. Run from the project directory."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from PIL import ImageGrab
from app import App, dpi_aware


def pump(root, seconds=.2):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        root.update()
        time.sleep(.01)


dpi_aware()
root = tk.Tk()
app = App(root)
try:
    pump(root)
    root.geometry("900x740")
    pump(root)
    assert app.cancel_button.winfo_rooty() + app.cancel_button.winfo_height() <= root.winfo_rooty() + root.winfo_height() - 35, "Controls clipped at minimum size"
    root.geometry("1100x740")
    pump(root)
    app.shape.set("圆形")
    app.custom.set(True)
    app.size_mode.set("resize")
    app.width.set("240")
    app.height.set("240")
    app.capture()
    pump(root, .7)
    assert app.overlay is not None, "Overlay failed to open"
    assert root.state() == "withdrawn"
    canvas = app.overlay.canvas
    canvas.event_generate("<ButtonPress-1>", x=120, y=120)
    canvas.event_generate("<B1-Motion>", x=420, y=420)
    canvas.event_generate("<ButtonRelease-1>", x=420, y=420)
    pump(root)
    assert app.image.size == (240, 240)
    assert app.image.getpixel((0, 0))[3] == 0
    assert root.state() == "normal"
    app.target.set("10")
    app.start_compress()
    deadline = time.monotonic() + 15
    while app.busy and time.monotonic() < deadline:
        pump(root)
    assert not app.busy and app.result and len(app.result) <= 10240
    previous = app.image
    app.capture()
    pump(root, .7)
    app.overlay.window.event_generate("<Button-3>", x=20, y=20)
    pump(root)
    assert app.overlay is None and root.state() == "normal"
    assert app.image is previous
    app.size_mode.set("fixed")
    app.shape.set("矩形")
    app.width.set("240")
    app.height.set("160")
    app.capture()
    pump(root, .7)
    overlay = app.overlay
    assert overlay is not None and app.capture_size is None
    x0, y0, x1, y1 = overlay.fixed
    assert (x1 - x0, y1 - y0) == (240, 160)
    overlay.canvas.event_generate("<ButtonPress-1>", x=x0 + 30, y=y0 + 30)
    overlay.canvas.event_generate("<B1-Motion>", x=x0 - 30, y=y0 - 10)
    overlay.canvas.event_generate("<ButtonRelease-1>", x=x0 - 30, y=y0 - 10)
    pump(root)
    assert app.overlay is overlay, "Releasing a fixed frame must not capture"
    assert overlay.fixed[:2] == (max(0, x0 - 60), max(0, y0 - 40))
    overlay.nudge((1, 0), 1)
    expected = overlay.screen.crop(overlay.fixed).convert("RGBA")
    overlay.window.event_generate("<Return>")
    pump(root)
    assert app.overlay is None and app.image.size == (240, 160)
    assert app.image.tobytes() == expected.tobytes(), "Fixed capture resampled pixels"
    app.capture()
    pump(root, .7)
    app.overlay.window.event_generate("<Button-3>", x=20, y=20)
    pump(root)
    assert app.overlay is None and root.state() == "normal"
    # Use a generated image in the saved preview, never desktop contents.
    from PIL import Image, ImageDraw
    sample = Image.new("RGBA", (1000, 660), "#ecf6f2")
    draw = ImageDraw.Draw(sample)
    draw.rectangle((70, 70, 930, 590), fill="#ffffff")
    draw.rectangle((110, 115, 440, 545), fill="#13846d")
    draw.ellipse((175, 240, 375, 440), fill="#f3c85b")
    for y, end in ((150, 840), (190, 760), (300, 860), (340, 780), (380, 830)):
        draw.rectangle((495, y, end, y + 16), fill="#c7d4d4")
    app.set_image(sample, "示例图片.png")
    app.target.set("80")
    app.start_compress()
    while app.busy:
        pump(root)
    pump(root)
    folder = Path("work")
    folder.mkdir(exist_ok=True)
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    pump(root, .5)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(folder / "ui-preview.png")
    print("PASS: hide, resize capture, movable fixed frame, exact pixels, Enter, compression, right-click cancel, restore, preview")
finally:
    root.destroy()
