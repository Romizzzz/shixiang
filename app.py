"""Screenshot and image size compressor for Windows."""
import ctypes
import math
import queue
import sys
import threading
import tkinter as tk
import warnings
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageGrab, ImageOps, ImageTk
from image_ops import compress, encode, fixed_box, make_capture, selection_box

SHAPES = {"矩形": "rectangle", "正方形": "square", "圆形": "circle", "椭圆": "ellipse"}
warnings.simplefilter("error", Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = 40_000_000


def dpi_aware():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)


class CaptureOverlay:
    def __init__(self, app, screen, origin):
        self.app, self.screen, self.start = app, screen, None
        self.fixed = None
        self.drag_origin = None
        if app.fixed_capture_size:
            fw, fh = app.fixed_capture_size
            pointer = app.root.winfo_pointerxy()
            self.fixed = fixed_box((pointer[0] - origin[0] - fw // 2,
                                    pointer[1] - origin[1] - fh // 2),
                                   (fw, fh), screen.size)
        self.window = tk.Toplevel(app.root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        w, h = screen.size
        self.window.geometry(f"{w}x{h}+0+0")
        self.window.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.window, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.photo = ImageTk.PhotoImage(screen)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.window.bind("<Button-3>", lambda e: self.close())
        self.window.bind("<Escape>", lambda e: self.close())
        if self.fixed:
            self.canvas.config(cursor="fleur")
            self.toolbar = ttk.Frame(self.canvas, padding=4)
            ttk.Label(self.toolbar, text=f"{fw} × {fh} px").pack(side="left", padx=8)
            ttk.Button(self.toolbar, text="确认截图", command=self.confirm, style="Accent.TButton").pack(side="left", padx=4)
            ttk.Button(self.toolbar, text="取消", command=self.close).pack(side="left")
            self.toolbar_id = self.canvas.create_window(0, 0, window=self.toolbar, anchor="nw")
            self.window.bind("<Return>", lambda e: self.confirm())
            for key, delta in (("Left", (-1, 0)), ("Right", (1, 0)),
                               ("Up", (0, -1)), ("Down", (0, 1))):
                self.window.bind(f"<{key}>", lambda e, d=delta: self.nudge(d, 1))
                self.window.bind(f"<Shift-{key}>", lambda e, d=delta: self.nudge(d, 10))
            self.draw_selection(self.fixed)
        self.window.deiconify()
        self.window.update_idletasks()
        # Win32 placement handles negative virtual-desktop coordinates directly.
        hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id())
        ctypes.windll.user32.SetWindowPos(hwnd, -1, origin[0], origin[1], w, h, 0x0040)
        self.window.focus_force()
        self.window.grab_set()

    def press(self, event):
        if self.fixed:
            x0, y0, x1, y1 = self.fixed
            if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
                return
            self.drag_origin = self.fixed[:2]
        self.start = (event.x, event.y)

    def box(self, event):
        return selection_box(self.start, (event.x, event.y), self.screen.size,
                             self.app.capture_shape in ("square", "circle"))

    def drag(self, event):
        if self.start is None:
            return
        if self.fixed:
            self.fixed = fixed_box((self.drag_origin[0] + event.x - self.start[0],
                                    self.drag_origin[1] + event.y - self.start[1]),
                                   self.app.fixed_capture_size, self.screen.size)
            self.draw_selection(self.fixed)
        else:
            self.draw_selection(self.box(event))

    def draw_selection(self, box):
        self.canvas.delete("selection")
        draw = self.canvas.create_oval if self.app.capture_shape in ("circle", "ellipse") else self.canvas.create_rectangle
        draw(*box, outline="#07966b", width=3, tags="selection")
        if self.fixed:
            self.toolbar.update_idletasks()
            tw, th = self.toolbar.winfo_reqwidth(), self.toolbar.winfo_reqheight()
            x = max(0, min(box[0], self.screen.width - tw))
            y = box[3] + 8
            if y + th > self.screen.height:
                y = max(0, box[1] - th - 8)
            self.canvas.coords(self.toolbar_id, x, y)
            self.canvas.tag_raise(self.toolbar_id)
        else:
            self.canvas.create_text(box[0] + 8, max(16, box[1] - 14), anchor="w",
                                    text=f"{box[2]-box[0]} × {box[3]-box[1]} px",
                                    fill="#078251", font=("Segoe UI", 12, "bold"), tags="selection")

    def nudge(self, delta, step):
        self.fixed = fixed_box((self.fixed[0] + delta[0] * step,
                                self.fixed[1] + delta[1] * step),
                               self.app.fixed_capture_size, self.screen.size)
        self.draw_selection(self.fixed)
        return "break"

    def confirm(self):
        self.finish(self.fixed)

    def release(self, event):
        if self.fixed:
            if self.start is not None:
                self.drag(event)
            self.start = None
            return
        if self.start is None:
            return
        box = self.box(event)
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            self.start = None
            return
        self.finish(box)

    def finish(self, box):
        try:
            image = make_capture(self.screen, box, self.app.capture_shape, self.app.capture_size)
            self.app.set_image(image, "新截图")
        except Exception as exc:
            messagebox.showerror("截图失败", str(exc), parent=self.window)
        finally:
            self.close()

    def close(self):
        self.window.grab_release()
        self.window.destroy()
        self.app.overlay = None
        self.app.restore()


class App:
    def __init__(self, root):
        self.root = root
        # Use pixel-sized UI metrics consistently with the pixel-sized workspace.
        root.tk.call("tk", "scaling", 96 / 72)
        root.title("拾像 · 截图与图片压缩")
        root.geometry("1100x740")
        root.minsize(900, 740)
        root.configure(bg="#f4f6f7")
        self.image = self.result = self.overlay = None
        self.busy = False
        self.events = queue.Queue()
        self.cancel = threading.Event()
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background="#f4f6f7", foreground="#263238")
        style.configure("TButton", padding=(12, 9), background="#e5eaed", borderwidth=0)
        style.map("TButton", background=[("active", "#d5e5df")])
        style.configure("Accent.TButton", background="#087f63", foreground="white")
        style.map("Accent.TButton", background=[("active", "#096b55"), ("disabled", "#b4c7bf")])
        style.configure("TEntry", padding=6, fieldbackground="white")
        style.configure("TCombobox", padding=6, fieldbackground="white")
        top = ttk.Frame(root, padding=(26, 22, 26, 16))
        top.pack(fill="x")
        ttk.Label(top, text="拾像", font=("Microsoft YaHei UI", 23, "bold")).pack(side="left")
        ttk.Label(top, text="截图 / 图片压缩", foreground="#647477").pack(side="left", padx=20)
        self.open_button = ttk.Button(top, text="打开图片", command=self.open_image)
        self.open_button.pack(side="right")
        body = ttk.Frame(root, padding=(26, 0, 26, 16))
        body.pack(fill="both", expand=True)
        controls = ttk.Frame(body, width=290)
        controls.pack(side="left", fill="y", padx=(0, 24))
        controls.pack_propagate(False)
        ttk.Label(controls, text="截图", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(4, 12))
        self.shape = tk.StringVar(value="矩形")
        ttk.Label(controls, text="选区形状").pack(anchor="w")
        ttk.Combobox(controls, textvariable=self.shape, values=list(SHAPES), state="readonly").pack(fill="x", pady=(5, 12))
        self.custom = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="自定义输出尺寸", variable=self.custom).pack(anchor="w")
        modes = ttk.Frame(controls)
        modes.pack(fill="x", pady=(4, 0))
        self.size_mode = tk.StringVar(value="fixed")
        self.mode_buttons = [
            ttk.Radiobutton(modes, text="固定截图框", variable=self.size_mode, value="fixed"),
            ttk.Radiobutton(modes, text="截图后缩放", variable=self.size_mode, value="resize"),
        ]
        for button in self.mode_buttons:
            button.pack(side="left", padx=(0, 12))
        dims = ttk.Frame(controls)
        dims.pack(fill="x", pady=(6, 8))
        self.width, self.height = tk.StringVar(value="800"), tk.StringVar(value="800")
        self.width_entry = ttk.Entry(dims, textvariable=self.width, width=7)
        self.width_entry.pack(side="left")
        ttk.Label(dims, text=" × ").pack(side="left")
        self.height_entry = ttk.Entry(dims, textvariable=self.height, width=7)
        self.height_entry.pack(side="left")
        ttk.Label(dims, text=" px").pack(side="left")
        self.custom.trace_add("write", lambda *_: self.update_size_controls())
        self.update_size_controls()
        self.capture_button = ttk.Button(controls, text="开始截图", style="Accent.TButton", command=self.capture)
        self.capture_button.pack(fill="x")
        ttk.Separator(controls).pack(fill="x", pady=10)
        ttk.Label(controls, text="压缩", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 12))
        ttk.Label(controls, text="文件大小上限").pack(anchor="w")
        target_row = ttk.Frame(controls)
        target_row.pack(fill="x", pady=(5, 12))
        self.target, self.unit = tk.StringVar(value="200"), tk.StringVar(value="KB")
        ttk.Entry(target_row, textvariable=self.target, width=13).pack(side="left", fill="x", expand=True)
        ttk.Combobox(target_row, textvariable=self.unit, values=["KB", "MB"], width=5, state="readonly").pack(side="left", padx=(8, 0))
        self.fmt = tk.StringVar(value="WEBP")
        ttk.Label(controls, text="输出格式").pack(anchor="w")
        ttk.Combobox(controls, textvariable=self.fmt, values=["WEBP", "JPEG", "PNG"], state="readonly").pack(fill="x", pady=(5, 10))
        self.resize = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="必要时允许缩小像素尺寸", variable=self.resize).pack(anchor="w", pady=(0, 12))
        self.compress_button = ttk.Button(controls, text="压到指定大小", command=self.start_compress, style="Accent.TButton", state="disabled")
        self.compress_button.pack(fill="x")
        self.cancel_button = ttk.Button(controls, text="取消压缩", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(fill="x", pady=(8, 0))
        preview = ttk.Frame(body)
        preview.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(preview)
        bar.pack(fill="x", pady=(4, 12))
        self.name = tk.StringVar(value="未选择图片")
        ttk.Label(bar, textvariable=self.name, font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        self.view = tk.StringVar(value="原图")
        self.view_combo = ttk.Combobox(bar, textvariable=self.view, values=["原图", "压缩结果"], state="readonly", width=9)
        self.view_combo.pack(side="right")
        self.view_combo.bind("<<ComboboxSelected>>", lambda e: self.render())
        self.canvas = tk.Canvas(preview, bg="#e9edef", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.details = tk.StringVar(value="")
        ttk.Label(preview, textvariable=self.details).pack(anchor="w", pady=12)
        bottom = ttk.Frame(preview)
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=100)
        self.progress.pack(side="left")
        self.save_button = ttk.Button(bottom, text="保存图片", command=self.save, state="disabled")
        self.save_button.pack(side="right")
        self.status = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.status, padding=(26, 10), foreground="#52645d").pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def update_size_controls(self):
        state = "normal" if self.custom.get() else "disabled"
        for control in (*self.mode_buttons, self.width_entry, self.height_entry):
            control.config(state=state)

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(150, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self.capture_button.config(state="normal")

    def capture(self):
        if self.busy:
            return
        try:
            self.capture_shape = SHAPES[self.shape.get()]
            self.capture_size = None
            self.fixed_capture_size = None
            if self.custom.get():
                w, h = int(self.width.get()), int(self.height.get())
                if min(w, h) < 1 or max(w, h) > 8192 or w * h > 20_000_000:
                    raise ValueError("宽高须为 1–8192 px，且总像素不超过 2000 万")
                if self.capture_shape in ("circle", "square") and w != h:
                    raise ValueError("圆形和正方形的输出宽高必须相同")
                if self.size_mode.get() == "fixed":
                    self.fixed_capture_size = (w, h)
                else:
                    self.capture_size = (w, h)
            self.capture_button.config(state="disabled")
            self.root.withdraw()
            self.root.after(350, self.grab)
        except ValueError as exc:
            messagebox.showerror("尺寸无效", str(exc), parent=self.root)

    def grab(self):
        try:
            screen = ImageGrab.grab(all_screens=True)
            user32 = ctypes.windll.user32
            origin = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
            self.overlay = CaptureOverlay(self, screen, origin)
        except Exception as exc:
            self.restore()
            messagebox.showerror("无法截屏", str(exc), parent=self.root)

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")])
        if not path:
            return
        try:
            with Image.open(path) as source:
                if getattr(source, "n_frames", 1) > 1:
                    raise ValueError("当前版本仅支持静态图片")
                image = ImageOps.exif_transpose(source).convert("RGBA")
            self.set_image(image, Path(path).name, Path(path).stat().st_size)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self.root)

    def set_image(self, image, name, byte_size=None):
        self.image, self.result = image, None
        self.source_bytes = byte_size
        self.name.set(name[:42])
        self.view.set("原图")
        self.compress_button.config(state="normal")
        self.save_button.config(state="normal")
        self.status.set("已载入图片")
        self.render()

    def render(self):
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.image is None:
            self.canvas.create_text(w // 2, h // 2, text="暂无图片", fill="#7c8b8f", font=("Microsoft YaHei UI", 16))
            return
        result = self.view.get() == "压缩结果" and self.result is not None
        image = self.result_image if result else self.image
        thumbnail = image.copy()
        thumbnail.thumbnail((max(1, w - 32), max(1, h - 32)), Image.Resampling.LANCZOS)
        tw, th = thumbnail.size
        checker = Image.new("RGBA", (tw, th), "#ffffff")
        from PIL import ImageDraw
        draw = ImageDraw.Draw(checker)
        for y in range(0, th, 16):
            for x in range(0, tw, 16):
                if (x // 16 + y // 16) % 2:
                    draw.rectangle((x, y, x + 15, y + 15), fill="#e1e5e7")
        checker.alpha_composite(thumbnail.convert("RGBA"))
        self.photo = ImageTk.PhotoImage(checker)
        self.canvas.create_image(w // 2, h // 2, image=self.photo)
        size = len(self.result) if result else self.source_bytes
        text = f"{image.width} × {image.height} px"
        if size is not None:
            text += f"  ·  {size / 1024:.2f} KB"
        if result:
            text += f"  ·  {self.result_format}"
        self.details.set(text)

    def set_busy(self, value):
        self.busy = value
        for button in (self.open_button, self.capture_button, self.compress_button, self.save_button):
            button.config(state="disabled" if value else "normal")
        self.cancel_button.config(state="normal" if value else "disabled")
        self.progress.start(15) if value else self.progress.stop()

    def start_compress(self):
        if self.image is None or self.busy:
            return
        try:
            amount = float(self.target.get())
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError()
            target = int(amount * (1024 if self.unit.get() == "KB" else 1024 * 1024))
            if target < 1024:
                raise ValueError()
        except ValueError:
            messagebox.showerror("目标无效", "请输入至少 1 KB 的有效大小", parent=self.root)
            return
        fmt = self.fmt.get()
        if fmt == "JPEG" and self.image.getchannel("A").getextrema()[0] < 255:
            if not messagebox.askokcancel("透明背景", "JPEG 会将透明区域填充为白色。是否继续？", parent=self.root):
                return
        image, resize = self.image.copy(), self.resize.get()
        self.cancel.clear()
        self.set_busy(True)
        self.status.set("正在压缩…")

        def worker():
            try:
                data, dimensions, quality = compress(image, target, fmt, resize, self.cancel.is_set)
                self.events.put(("done", (data, dimensions, quality, fmt, target)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, payload = self.events.get_nowait()
            self.set_busy(False)
            if kind == "done" and not self.cancel.is_set():
                self.result, dimensions, quality, self.result_format, target = payload
                with Image.open(BytesIO(self.result)) as decoded:
                    self.result_image = decoded.convert("RGBA")
                self.view.set("压缩结果")
                self.render()
                self.status.set(f"达标：{len(self.result):,} / {target:,} 字节"
                                + (f" · 质量 {quality}" if quality else "")
                                + (" · 已缩小尺寸" if dimensions != self.image.size else " · 原尺寸"))
            else:
                self.status.set("已取消压缩" if self.cancel.is_set() else payload)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def save(self):
        result = self.view.get() == "压缩结果" and self.result is not None
        fmt = self.result_format if result else "PNG"
        ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]
        path = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(fmt, "*" + ext)],
                                          initialfile=f"shixiang-{datetime.now():%Y%m%d-%H%M%S}{ext}")
        if path:
            try:
                data = self.result if result else encode(self.image, "PNG")
                Path(path).write_bytes(data)
                self.status.set(f"已保存：{path}")
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.root)

    def close(self):
        self.cancel.set()
        self.root.destroy()


if __name__ == "__main__":
    dpi_aware()
    App(tk.Tk()).root.mainloop()
