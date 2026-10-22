from __future__ import annotations

import queue
import math
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
import ctypes
from array import array
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import jmcomic
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

try:
    import future_ui as ui_art
except Exception:  # pragma: no cover - artwork is optional decoration
    ui_art = None


APP_NAME = "未来漫境"
APP_VERSION = "1.0.1.1122"
IMAGE_EXTENSIONS = {".png", ".webp", ".gif", ".jpg", ".bmp", ".jpeg"}
MAX_IMAGE_PIXELS = 8_000_000
MAX_IMAGE_SIDE = 4_000
READER_BATCH_SIZE = 16
GOLDEN_OFFSET_RATIO = (math.sqrt(5.0) - 1.0) / 2.0

FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Cascadia Mono"
ctk.ThemeManager.theme["CTkFont"].update({"family": FONT_FAMILY, "size": 12, "weight": "normal"})

BG = "#F6F0F4"
SIDEBAR = "#221C33"
SIDEBAR_ACTIVE = "#3A3050"
SIDEBAR_HOVER = "#2E2643"
SIDEBAR_LINE = "#372D4C"
SIDEBAR_TEXT = "#D8D1E6"
SIDEBAR_MUTED = "#9B90B6"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#FBF7FA"
SURFACE_ALT = "#F4ECF3"
STROKE = "#F0E6ED"
STROKE_STRONG = "#E3D6E2"
INPUT_BG = "#FCF9FC"
INPUT_STROKE = "#EADFEA"
TEXT = "#2C2438"
TEXT_SOFT = "#564C68"
MUTED = "#847A95"
FAINT = "#AEA3BB"
ACCENT = "#D9678F"
ACCENT_HOVER = "#C85680"
ACCENT_SOFT = "#FCEBF1"
ACCENT_LILAC = "#7B6AD8"
ACCENT_LILAC_HOVER = "#6B5AC8"
LILAC_SOFT = "#F2EEFC"
DANGER = "#C05064"
SUCCESS = "#3E8F70"
WARN = "#A9761F"
LOG_BG = "#211B31"
LOG_TEXT = "#F0EAF7"
READER_PAPER = "#FBF4EF"

HERO = "#251E3A"
HERO_SOFT = "#3A2F55"
HERO_LINE = "#43375E"
HERO_TEXT = "#FBF7FF"
HERO_MUTED = "#BFB3D2"
HERO_FAINT = "#9E90B8"


def nav_badge(char: str, background: str, foreground: str, size: int = 26) -> ctk.CTkImage:
    """Tiny rounded character chip used as the sidebar navigation icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=8, fill=background)
    font = None
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
        try:
            font = ImageFont.truetype(candidate, 12)
            break
        except Exception:
            continue
    if font is not None:
        draw.text((size / 2, size / 2 + 0.5), char, font=font, fill=foreground, anchor="mm")
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


class PillSwitch(ctk.CTkFrame):
    """Compact option switch: a soft track with a raised active pill."""

    def __init__(self, master, values, variable, command=None, *, height: int = 42, font_size: int = 10):
        super().__init__(
            master,
            fg_color=SURFACE_ALT,
            corner_radius=13,
            height=height,
            border_width=1,
            border_color=STROKE,
        )
        self.grid_propagate(False)
        self._variable = variable
        self._command = command
        self._buttons: dict[str, ctk.CTkButton] = {}
        for index, value in enumerate(values):
            self.grid_columnconfigure(index, weight=1)
            button = ctk.CTkButton(
                self,
                text=value,
                height=max(24, height - 8),
                corner_radius=10,
                fg_color="transparent",
                hover_color="#EADFEA",
                text_color=MUTED,
                font=(FONT_FAMILY, font_size),
                command=lambda item=value: self._select(item),
            )
            button.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            self._buttons[value] = button
        self._variable.trace_add("write", self._sync)
        self._sync()

    def _sync(self, *_args) -> None:
        current = self._variable.get()
        for value, button in self._buttons.items():
            active = value == current
            button.configure(
                fg_color=SURFACE if active else "transparent",
                text_color=ACCENT if active else MUTED,
                hover_color=SURFACE if active else "#EADFEA",
            )

    def _select(self, value: str) -> None:
        self._variable.set(value)
        if self._command is not None:
            self._command(value)

    def configure(self, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            for button in self._buttons.values():
                button.configure(state=state)
        if kwargs:
            super().configure(**kwargs)


def app_directory() -> Path:
    executable = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(executable).resolve().parent


def resource_path(name: str) -> Path:
    bundle = Path(getattr(sys, "_MEIPASS", app_directory()))
    return bundle / name


def set_app_icon(window) -> None:
    icon = resource_path("JMDownloader.ico")
    if icon.is_file():
        try:
            window.iconbitmap(default=str(icon))
        except Exception:
            try:
                window.iconbitmap(str(icon))
            except Exception:
                pass
    brand = resource_path("JMDownloader-icon-preview.png")
    if brand.is_file():
        try:
            with Image.open(brand) as source:
                image = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            window.iconphoto(True, photo)
            window._jm_window_icon = photo
        except Exception:
            pass


def apply_dark_titlebar(window) -> None:
    """Paint the native caption in the same deep plum as the sidebar."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2) or window.winfo_id()
        enabled = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (19 on older Windows 10 builds)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
            ) == 0:
                break
        for attribute, color in (
            (35, 0x003A1E25),  # caption, COLORREF is BGR
            (36, 0x00FFF7FB),  # caption text
            (34, 0x005E3743),  # border
        ):
            value = ctypes.c_int(color)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass


def polish_entry(entry: ctk.CTkEntry, normal: str = INPUT_STROKE, focus: str = ACCENT) -> None:
    def enter(_event=None):
        try:
            entry.configure(border_color=focus)
        except Exception:
            pass

    def leave(_event=None):
        try:
            entry.configure(border_color=normal)
        except Exception:
            pass

    entry.bind("<FocusIn>", enter, add="+")
    entry.bind("<FocusOut>", leave, add="+")


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def image_files(folder: Path) -> list[Path]:
    """List supported images directly inside one comic folder; never recurse through a library root."""
    try:
        candidates = (
            item for item in folder.iterdir()
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
        )
        return sorted(candidates, key=natural_key)
    except OSError:
        return []


def gilbert_order(width: int, height: int, progress=None) -> array:
    """Return the same rectangular Gilbert traversal used by the Android image tool."""
    total = width * height
    order = array("I")
    notify_every = max(1, total // 100)

    def emit(x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= width or y >= height or len(order) >= total:
            raise ValueError("图片路径生成越界")
        order.append(y * width + x)
        if progress is not None and (len(order) % notify_every == 0 or len(order) == total):
            progress(len(order))

    def generate(x: int, y: int, ax: int, ay: int, bx: int, by: int) -> None:
        w = abs(ax + ay)
        h = abs(bx + by)
        dax = (ax > 0) - (ax < 0)
        day = (ay > 0) - (ay < 0)
        dbx = (bx > 0) - (bx < 0)
        dby = (by > 0) - (by < 0)

        if h == 1:
            for _ in range(w):
                emit(x, y)
                x += dax
                y += day
            return
        if w == 1:
            for _ in range(h):
                emit(x, y)
                x += dbx
                y += dby
            return

        ax2, ay2 = ax // 2, ay // 2
        bx2, by2 = bx // 2, by // 2
        w2 = abs(ax2 + ay2)
        h2 = abs(bx2 + by2)
        if 2 * w > 3 * h:
            if w2 % 2 and w > 2:
                ax2 += dax
                ay2 += day
            generate(x, y, ax2, ay2, bx, by)
            generate(x + ax2, y + ay2, ax - ax2, ay - ay2, bx, by)
        else:
            if h2 % 2 and h > 2:
                bx2 += dbx
                by2 += dby
            generate(x, y, bx2, by2, ax2, ay2)
            generate(x + bx2, y + by2, ax, ay, bx - bx2, by - by2)
            generate(
                x + (ax - dax) + (bx2 - dbx),
                y + (ay - day) + (by2 - dby),
                -bx2,
                -by2,
                -(ax - ax2),
                -(ay - ay2),
            )

    if width >= height:
        generate(0, 0, width, 0, 0, height)
    else:
        generate(0, 0, 0, height, width, 0)
    if len(order) != total:
        raise ValueError("像素路径长度不匹配")
    return order


class ImageReader(ctk.CTkToplevel):
    def __init__(
        self,
        parent: "DownloaderApp",
        folder: Path,
        files: list[Path] | None = None,
        start_file: Path | None = None,
    ):
        super().__init__(parent)
        self.folder = folder
        self.files: list[Path] = list(files) if files is not None else []
        self._initial_file_index = self.files.index(start_file) if start_file in self.files else 0
        self.batch_size = READER_BATCH_SIZE
        self.batch_start = 0
        self.batch_loading = False
        self._batch_scroll_to_end = False
        self._batch_scroll_to_index: int | None = None
        self._load_generation = 0
        self._reader_events: queue.Queue[tuple] = queue.Queue()
        self.source_images: list[Image.Image] = []
        self.images: list[ctk.CTkImage] = []
        self.image_labels: list[ctk.CTkLabel] = []
        self.zoom = 1.0
        self.reader_theme = "暖纸"
        self.fullscreen = False
        self.title(f"漫画阅读器 · {folder.name}")
        self.geometry("1080x900")
        self.windowed_geometry = self.geometry()
        self.minsize(820, 620)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        set_app_icon(self)
        self.bind("<Home>", lambda _event: self._go_to_top())
        self.bind("<End>", lambda _event: self.pages._parent_canvas.yview_moveto(1))
        self.bind("<Control-plus>", lambda _event: self._change_zoom(0.1))
        self.bind("<Control-equal>", lambda _event: self._change_zoom(0.1))
        self.bind("<Control-minus>", lambda _event: self._change_zoom(-0.1))
        self.bind("<F11>", lambda _event: self._toggle_fullscreen())
        self.bind("<Escape>", lambda _event: self._exit_fullscreen())

        top = ctk.CTkFrame(self, fg_color=HERO, corner_radius=18, height=100)
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        top.grid_propagate(False)
        top.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(top, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="nw", padx=22, pady=(12, 10))
        ctk.CTkLabel(
            title_box,
            text="READING ROOM · 未来漫境",
            font=(FONT_FAMILY, 9, "bold"),
            text_color="#C9A6D8",
            height=14,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box,
            text=folder.name,
            font=(FONT_FAMILY, 18, "bold"),
            text_color=HERO_TEXT,
            height=30,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.count_label = ctk.CTkLabel(
            title_box, text="正在整理图片…", font=(FONT_FAMILY, 9), text_color=HERO_MUTED, height=16
        )
        self.count_label.grid(row=2, column=0, sticky="w", pady=(2, 0))
        hint_box = ctk.CTkFrame(top, fg_color="transparent")
        hint_box.grid(row=0, column=1, sticky="e", padx=22, pady=(15, 12))
        ctk.CTkLabel(
            hint_box,
            text="本地阅读",
            font=(FONT_FAMILY, 9),
            text_color="#F4C9DB",
            fg_color=HERO_SOFT,
            corner_radius=9,
            height=24,
        ).pack(anchor="e")
        ctk.CTkLabel(
            hint_box,
            text="滚轮连续阅读 · Ctrl +/− 缩放 · F11 全屏",
            font=(FONT_FAMILY, 9),
            text_color=HERO_FAINT,
        ).pack(anchor="e", pady=(7, 0))

        toolbar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=STROKE)
        toolbar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)
        controls = ctk.CTkFrame(toolbar, fg_color="transparent")
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(9, 3))

        nav_group = ctk.CTkFrame(controls, fg_color="transparent")
        nav_group.pack(side="left")
        self._reader_button(nav_group, "‹  上一张", self._scroll_adjacent_image, width=82).pack(side="left", padx=(0, 4))
        self._reader_button(nav_group, "下一张  ›", lambda: self._scroll_adjacent_image(1), width=82).pack(side="left")

        ctk.CTkFrame(controls, fg_color="transparent", height=1).pack(side="left", expand=True, fill="x")

        zoom_group = ctk.CTkFrame(controls, fg_color="transparent")
        zoom_group.pack(side="left")
        self._reader_button(zoom_group, "−", lambda: self._change_zoom(-0.1), width=34).pack(side="left")
        self.zoom_label = ctk.CTkLabel(
            zoom_group, text="100%", width=52, font=(FONT_FAMILY, 10), text_color=TEXT
        )
        self.zoom_label.pack(side="left", padx=2)
        self._reader_button(zoom_group, "+", lambda: self._change_zoom(0.1), width=34).pack(side="left")
        self._reader_button(zoom_group, "适配宽度", self._fit_width, width=80).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(controls, fg_color="transparent", height=1).pack(side="left", expand=True, fill="x")

        look_group = ctk.CTkFrame(controls, fg_color="transparent")
        look_group.pack(side="left")
        self.theme_button = self._reader_button(look_group, "背景 · 暖纸", self._toggle_theme, width=96)
        self.theme_button.pack(side="left")
        self._reader_button(look_group, "回到顶部", self._go_to_top, width=80).pack(side="left", padx=4)
        self.fullscreen_button = self._reader_button(
            look_group, "沉浸模式", self._toggle_fullscreen, width=86, accent=True
        )
        self.fullscreen_button.pack(side="left", padx=(4, 0))

        self.progress = ctk.CTkProgressBar(
            toolbar, height=6, corner_radius=4, progress_color=ACCENT, fg_color=SURFACE_ALT
        )
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=(14, 6), pady=(2, 8))
        self.progress_label = ctk.CTkLabel(
            toolbar, text="0%", width=38, font=(FONT_FAMILY, 9), text_color=MUTED
        )
        self.progress_label.grid(row=1, column=1, sticky="e", padx=(0, 14), pady=(2, 8))

        batch_row = ctk.CTkFrame(toolbar, fg_color="transparent")
        batch_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 9))
        batch_row.grid_columnconfigure(1, weight=1)
        self.batch_prev_button = self._reader_button(batch_row, "上一组", self._show_previous_batch, width=72)
        self.batch_prev_button.grid(row=0, column=0, sticky="w")
        self.batch_range_label = ctk.CTkLabel(
            batch_row, text="等待扫描", font=(FONT_FAMILY, 9), text_color=MUTED
        )
        self.batch_range_label.grid(row=0, column=1)
        self.batch_next_button = self._reader_button(batch_row, "下一组", self._show_next_batch, width=72)
        self.batch_next_button.grid(row=0, column=2, sticky="e")
        self.batch_prev_button.configure(state="disabled")
        self.batch_next_button.configure(state="disabled")

        self.pages = ctk.CTkScrollableFrame(
            self, fg_color=READER_PAPER, corner_radius=18, scrollbar_button_color="#D6C9CE",
            scrollbar_button_hover_color=ACCENT, scrollbar_fg_color="#F7EDE8",
        )
        self.pages.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.pages.grid_columnconfigure(0, weight=1)
        self.pages._parent_canvas.bind("<MouseWheel>", self._schedule_progress_update, add="+")
        self.pages._parent_canvas.bind("<Configure>", self._schedule_progress_update, add="+")
        self.after(50, self._drain_reader_events)
        self.after(50, self.load_images)
        self.after(80, lambda: apply_dark_titlebar(self))

    @staticmethod
    def _reader_button(parent, text: str, command, *, width: int = 80, accent: bool = False) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=32,
            corner_radius=9,
            fg_color=ACCENT if accent else SURFACE_ALT,
            hover_color=ACCENT_HOVER if accent else STROKE,
            text_color="#FFFFFF" if accent else TEXT,
            font=(FONT_FAMILY, 9),
            command=command,
        )

    def load_images(self) -> None:
        if not self.files:
            self.files = image_files(self.folder)
        if not self.files:
            self.count_label.configure(text="这个文件夹里没有可阅读的图片。请选择具体漫画文件夹。")
            self.batch_range_label.configure(text="未找到图片")
            return
        self.count_label.configure(text=f"找到 {len(self.files):,} 张图片，分组载入以控制内存。")
        initial = self._initial_file_index
        self._request_batch((initial // self.batch_size) * self.batch_size, scroll_to_index=initial)

    def _request_batch(
        self,
        start: int,
        *,
        scroll_to_end: bool = False,
        scroll_to_index: int | None = None,
    ) -> None:
        if self.batch_loading or not self.files:
            return
        start = max(0, min(start, len(self.files) - 1))
        self._load_generation += 1
        generation = self._load_generation
        self.batch_loading = True
        self.batch_start = start
        self._batch_scroll_to_end = scroll_to_end
        self._batch_scroll_to_index = scroll_to_index
        end = min(start + self.batch_size, len(self.files))
        self.batch_range_label.configure(text=f"正在读取 {start + 1:,}–{end:,} / {len(self.files):,} 张…")
        self.count_label.configure(text="正在载入图片…")
        self._clear_rendered_pages()
        self._set_batch_navigation()
        paths = self.files[start:end]
        threading.Thread(
            target=self._reader_batch_worker,
            args=(generation, start, paths),
            daemon=True,
            name="FutureRealm-ReaderBatch",
        ).start()

    def _reader_batch_worker(self, generation: int, start: int, paths: list[Path]) -> None:
        loaded: list[Image.Image] = []
        skipped = 0
        for image_path in paths:
            try:
                with Image.open(image_path) as source:
                    source.draft("RGB", (900, 1800))
                    image = ImageOps.exif_transpose(source)
                    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                        rgba = image.convert("RGBA")
                        paper = Image.new("RGBA", rgba.size, "#FFFFFF")
                        image = Image.alpha_composite(paper, rgba).convert("RGB")
                    else:
                        image = image.convert("RGB")
                    image.thumbnail((900, 1800), Image.Resampling.LANCZOS)
                    loaded.append(image.copy())
            except Exception:
                skipped += 1
        self._reader_events.put(("loaded", generation, start, len(paths), loaded, skipped))

    def _drain_reader_events(self) -> None:
        try:
            while True:
                event = self._reader_events.get_nowait()
                if event[0] != "loaded" or event[1] != self._load_generation:
                    continue
                _, _generation, start, requested, loaded, skipped = event
                self.batch_loading = False
                self.batch_start = start
                self.source_images = loaded
                self._render_images()
                first = start + 1
                last = min(start + requested, len(self.files))
                self.batch_range_label.configure(text=f"显示 {first:,}–{last:,} / {len(self.files):,} 张")
                detail = f"当前连续显示 {len(loaded)} 张"
                if skipped:
                    detail += f" · 跳过 {skipped} 张无法读取的图片"
                self.count_label.configure(text=f"{self.folder.name} · 共 {len(self.files):,} 张 · {detail}")
                self._set_batch_navigation()
                if self._batch_scroll_to_end:
                    self.after_idle(lambda: self.pages._parent_canvas.yview_moveto(1))
                elif self._batch_scroll_to_index is not None:
                    target_index = self._batch_scroll_to_index
                    self.after_idle(lambda index=target_index: self._scroll_to_index(index))
                else:
                    self.after_idle(lambda: self.pages._parent_canvas.yview_moveto(0))
                self._batch_scroll_to_end = False
                self._batch_scroll_to_index = None
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(60, self._drain_reader_events)

    def _clear_rendered_pages(self) -> None:
        for label in self.image_labels:
            label.destroy()
        self.image_labels.clear()
        self.images.clear()
        self.source_images.clear()

    def _set_batch_navigation(self) -> None:
        previous = self.batch_loading or self.batch_start <= 0
        following = self.batch_loading or self.batch_start + self.batch_size >= len(self.files)
        self.batch_prev_button.configure(state="disabled" if previous else "normal")
        self.batch_next_button.configure(state="disabled" if following else "normal")

    def _scroll_to_index(self, index: int) -> None:
        local_index = index - self.batch_start
        if not 0 <= local_index < len(self.image_labels):
            return
        self.update_idletasks()
        canvas = self.pages._parent_canvas
        region = canvas.cget("scrollregion").split()
        content_height = float(region[3]) if len(region) == 4 else 1.0
        position = self.image_labels[local_index].winfo_y()
        canvas.yview_moveto(max(0.0, min(1.0, position / max(1.0, content_height))))
        self.after_idle(self._update_progress)

    def _show_previous_batch(self) -> None:
        if self.batch_start > 0:
            self._request_batch(max(0, self.batch_start - self.batch_size), scroll_to_end=True)

    def _show_next_batch(self) -> None:
        if self.batch_start + self.batch_size < len(self.files):
            self._request_batch(self.batch_start + self.batch_size)

    def _render_images(self) -> None:
        for label in self.image_labels:
            label.destroy()
        self.image_labels.clear()
        self.images.clear()
        for row, source in enumerate(self.source_images):
            width = max(1, round(source.width * self.zoom))
            height = max(1, round(source.height * self.zoom))
            image = source if self.zoom == 1.0 else source.resize((width, height), Image.Resampling.LANCZOS)
            visual = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            label = ctk.CTkLabel(self.pages, text="", image=visual, fg_color="transparent")
            label.grid(row=row, column=0, pady=0)
            self.images.append(visual)
            self.image_labels.append(label)
        self.zoom_label.configure(text=f"{round(self.zoom * 100)}%")
        self.after(80, self._update_progress)

    def _change_zoom(self, amount: float) -> None:
        new_zoom = round(min(1.6, max(0.6, self.zoom + amount)), 2)
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self._render_images()

    def _fit_width(self) -> None:
        canvas_width = max(1, self.pages._parent_canvas.winfo_width() - 28)
        widest = max((image.width for image in self.source_images), default=900)
        self.zoom = min(1.0, canvas_width / widest)
        self._render_images()

    def _toggle_theme(self) -> None:
        if self.reader_theme == "暖纸":
            self.reader_theme = "深色"
            self.pages.configure(
                fg_color="#29273D",
                scrollbar_fg_color="#37344E",
                scrollbar_button_color="#716B8D",
                scrollbar_button_hover_color=ACCENT_LILAC,
            )
            self.theme_button.configure(text="背景 · 深色")
        else:
            self.reader_theme = "暖纸"
            self.pages.configure(
                fg_color=READER_PAPER,
                scrollbar_fg_color="#F5ECE9",
                scrollbar_button_color="#C9BFC9",
                scrollbar_button_hover_color=ACCENT,
            )
            self.theme_button.configure(text="背景 · 暖纸")

    def _go_to_top(self) -> None:
        self.pages._parent_canvas.yview_moveto(0)
        self.after_idle(self._update_progress)

    def _scroll_adjacent_image(self, direction: int = -1) -> None:
        if not self.image_labels:
            return
        self.update_idletasks()
        canvas = self.pages._parent_canvas
        region = canvas.cget("scrollregion").split()
        content_height = float(region[3]) if len(region) == 4 else 1.0
        current_top = canvas.yview()[0] * max(1.0, content_height)
        positions = [label.winfo_y() for label in self.image_labels]
        if direction > 0:
            target = next((position for position in positions if position > current_top + 24), None)
        else:
            target = next((position for position in reversed(positions) if position < current_top - 24), None)
        if target is not None:
            canvas.yview_moveto(max(0.0, min(1.0, target / max(1.0, content_height))))
            self.after_idle(self._update_progress)
        elif direction > 0:
            self._show_next_batch()
        else:
            self._show_previous_batch()

    def _toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self._exit_fullscreen()
            return
        self.windowed_geometry = self.geometry()
        self.fullscreen = True
        self.attributes("-fullscreen", True)
        self.fullscreen_button.configure(text="退出全屏")

    def _exit_fullscreen(self) -> None:
        if not self.fullscreen:
            return
        self.fullscreen = False
        self.attributes("-fullscreen", False)
        self.state("normal")
        self.geometry(self.windowed_geometry)
        self.fullscreen_button.configure(text="沉浸模式")
        self.after(80, self._restore_windowed_geometry)

    def _restore_windowed_geometry(self) -> None:
        if not self.winfo_exists() or self.fullscreen:
            return
        self.attributes("-fullscreen", False)
        self.state("normal")
        self.geometry(self.windowed_geometry)
        self.lift()
        self.focus_force()

    def _schedule_progress_update(self, _event=None) -> None:
        self.after(80, self._update_progress)

    def _update_progress(self) -> None:
        if not self.files:
            return
        canvas = self.pages._parent_canvas
        start, end = canvas.yview()
        scrollable = max(0.001, 1.0 - (end - start))
        local = min(1.0, max(0.0, start / scrollable))
        value = (self.batch_start + local * max(1, len(self.source_images))) / len(self.files)
        value = min(1.0, max(0.0, value))
        self.progress.set(value)
        self.progress_label.configure(text=f"{round(value * 100)}%")


class DownloaderApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__()
        set_app_icon(self)
        self.title(APP_NAME)
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        window_width = min(1240, max(1080, screen_width - 260))
        window_height = min(880, max(760, screen_height - 180))
        offset_x = max(0, (screen_width - window_width) // 2)
        offset_y = max(0, (screen_height - window_height) // 2 - 24)
        self.geometry(f"{window_width}x{window_height}+{offset_x}+{offset_y}")
        self.minsize(1080, 760)
        self.configure(fg_color=BG)

        self.output = ctk.StringVar(value=str(app_directory() / "JMD"))
        self.mode = ctk.StringVar(value="单本下载")
        self.events: queue.Queue[tuple] = queue.Queue()
        self.reader_scan_generation = 0
        self.reader_scan_root: Path | None = None
        self.reader_scan_current: Path | None = None
        self.reader_scan_results: list[tuple[str, Path, int]] = []
        self.reader_scan_visible: list[tuple[str, Path, int]] = []
        self.stop_event = threading.Event()
        self.running = False
        self.obf_busy = False
        self.hidden_busy = False
        self.obf_source: Image.Image | None = None
        self.obf_current: Image.Image | None = None
        self.obf_path: Path | None = None
        self.obf_photo = None
        self.obf_result_tag = "原图"
        self.obf_mode = ctk.StringVar(value="混淆")
        self.total = 0
        self.completed = 0
        self.current_id = ""
        self.page_name = "download"
        self._visible_page: str | None = None
        self._page_transition_job = None
        self._page_transition_target: str | None = None
        self._page_transition_token = 0
        self._nav_bars: dict[str, ctk.CTkFrame] = {}
        self._card_icon_cache: dict[tuple[str, str], ctk.CTkImage] = {}
        self._prepare_images()

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self.show_page("download", animate=False)
        self.after(100, self._drain_events)
        self.after(60, lambda: apply_dark_titlebar(self))

    def _prepare_images(self) -> None:
        """Build the small piece of vector artwork the interface needs."""
        self._brand_image = None
        self._brand_glow = None
        self._about_image = None
        self._hero_image = None
        self._sidebar_image = None
        self._nook_image = None
        self._scan_empty_image = None
        brand = resource_path("JMDownloader-icon-preview.png")
        try:
            if brand.is_file():
                with Image.open(brand) as source:
                    icon = source.convert("RGBA")
                    self._brand_image = ctk.CTkImage(
                        light_image=icon.resize((52, 52), Image.Resampling.LANCZOS),
                        dark_image=icon.resize((52, 52), Image.Resampling.LANCZOS),
                        size=(52, 52),
                    )
                    self._about_image = ctk.CTkImage(
                        light_image=icon.resize((44, 44), Image.Resampling.LANCZOS),
                        dark_image=icon.resize((44, 44), Image.Resampling.LANCZOS),
                        size=(44, 44),
                    )
        except Exception:
            pass
        if ui_art is None:
            return
        try:
            glow_art = ui_art.glow(92, "#E27FA2", 48)
            self._brand_glow = ctk.CTkImage(light_image=glow_art, dark_image=glow_art, size=(92, 92))
            hero_art = ui_art.hero_art(470, 164)
            self._hero_image = ctk.CTkImage(light_image=hero_art, dark_image=hero_art, size=(470, 164))
            sidebar_art = ui_art.sidebar_art(200, 142)
            self._sidebar_image = ctk.CTkImage(light_image=sidebar_art, dark_image=sidebar_art, size=(200, 142))
            nook_art = ui_art.reading_nook(420, 158)
            self._nook_image = ctk.CTkImage(light_image=nook_art, dark_image=nook_art, size=(420, 158))
            scan_art = ui_art.empty_scan_art(72)
            self._scan_empty_image = ctk.CTkImage(light_image=scan_art, dark_image=scan_art, size=(72, 72))
        except Exception:
            pass

    def _card_image(self, icon: str, tone: str = "rose") -> ctk.CTkImage | None:
        if ui_art is None:
            return None
        key = (icon, tone)
        image = self._card_icon_cache.get(key)
        if image is None:
            art = ui_art.card_icon(icon, tone, 34)
            image = ctk.CTkImage(light_image=art, dark_image=art, size=(34, 34))
            self._card_icon_cache[key] = image
        return image

    def _card(self, parent, title: str, subtitle: str | None = None, *, icon: str | None = None, tone: str = "rose") -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=22, border_width=1, border_color=STROKE)
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(15, 10))
        head.grid_columnconfigure(1, weight=1)
        icon_image = self._card_image(icon, tone) if icon else None
        title_column = 0
        if icon_image is not None:
            ctk.CTkLabel(head, text="", image=icon_image, fg_color="transparent", width=34, height=34).grid(
                row=0, column=0, rowspan=2, padx=(0, 11)
            )
            title_column = 1
        ctk.CTkLabel(
            head,
            text=title,
            font=(FONT_FAMILY, 15, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=title_column, sticky="w")
        if subtitle:
            subtitle_label = ctk.CTkLabel(
                head,
                text=subtitle,
                font=(FONT_FAMILY, 10),
                text_color=MUTED,
                anchor="w",
                justify="left",
                wraplength=360 if icon_image is not None else 420,
            )
            subtitle_label.grid(row=1, column=title_column, sticky="w", pady=(3, 0))

            def wrap_subtitle(event, label=subtitle_label, inset=100 if icon_image is not None else 44):
                width = max(160, int(event.width) - inset)
                if abs(int(label.cget("wraplength")) - width) > 4:
                    label.configure(wraplength=width)

            card.bind("<Configure>", wrap_subtitle, add="+")
        return card

    @staticmethod
    def _short_path(path: str, segments: int = 2) -> str:
        text = str(path)
        parts = [part for part in text.replace("\\", "/").split("/") if part]
        if len(parts) <= segments:
            return text
        return "…\\" + "\\".join(parts[-segments:])

    def _small_icon(self, icon: str, tone: str = "plum", size: int = 18) -> ctk.CTkImage | None:
        if ui_art is None:
            return None
        key = (f"{icon}@{size}", tone)
        image = self._card_icon_cache.get(key)
        if image is None:
            art = ui_art.card_icon(icon, tone, size)
            image = ctk.CTkImage(light_image=art, dark_image=art, size=(size, size))
            self._card_icon_cache[key] = image
        return image

    def _nav_button(self, row: int, label: str, badge: str, page: str, icon: str) -> ctk.CTkButton:
        if ui_art is not None:
            idle_icon = ctk.CTkImage(
                light_image=ui_art.nav_tile(icon, False),
                dark_image=ui_art.nav_tile(icon, False),
                size=(30, 30),
            )
            active_icon = ctk.CTkImage(
                light_image=ui_art.nav_tile(icon, True),
                dark_image=ui_art.nav_tile(icon, True),
                size=(30, 30),
            )
        else:
            idle_icon = nav_badge(badge, "#332D4C", "#A9A2C6")
            active_icon = nav_badge(badge, ACCENT, "#FFFFFF")
        self._nav_idle_icon[page] = idle_icon
        self._nav_active_icon[page] = active_icon

        shell = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=48)
        shell.grid(row=row, column=0, sticky="ew", padx=14, pady=3)
        shell.grid_propagate(False)
        bar = ctk.CTkFrame(shell, width=3, height=22, corner_radius=2, fg_color=ACCENT)
        bar.place(x=3, y=13)
        bar.place_forget()
        self._nav_bars[page] = bar
        button = ctk.CTkButton(
            shell,
            text=f"  {label}",
            image=idle_icon,
            compound="left",
            anchor="w",
            height=44,
            corner_radius=13,
            fg_color="transparent",
            hover_color=SIDEBAR_HOVER,
            text_color=SIDEBAR_TEXT,
            font=(FONT_FAMILY, 12),
            command=lambda: self.show_page(page),
        )
        button.pack(fill="both", expand=True, padx=(10, 4), pady=2)
        return button

    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, width=248, corner_radius=0, fg_color=SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(6, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(25, 18))
        brand.grid_columnconfigure(1, weight=1)
        mark = ctk.CTkFrame(brand, width=56, height=56, fg_color="transparent")
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        mark.grid_propagate(False)
        if self._brand_glow is not None:
            ctk.CTkLabel(mark, text="", image=self._brand_glow, fg_color="transparent").place(
                relx=0.5, rely=0.5, anchor="center"
            )
        if self._brand_image is not None:
            ctk.CTkLabel(mark, text="", image=self._brand_image, fg_color="transparent").place(
                relx=0.5, rely=0.5, anchor="center"
            )
        else:
            ctk.CTkLabel(
                mark,
                text="漫",
                width=52,
                height=52,
                corner_radius=15,
                fg_color=ACCENT_LILAC,
                text_color="#FFFFFF",
                font=(FONT_FAMILY, 17, "bold"),
            ).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(brand, text="未来漫境", font=(FONT_FAMILY, 17, "bold"), text_color="#FBF8FF").grid(
            row=0, column=1, sticky="sw"
        )
        ctk.CTkLabel(brand, text="未来不是未来 · 创作者", font=(FONT_FAMILY, 9), text_color="#A99CC2").grid(
            row=1, column=1, sticky="nw", pady=(3, 0)
        )

        ctk.CTkFrame(self.sidebar, height=1, fg_color=SIDEBAR_LINE).grid(
            row=1, column=0, sticky="ew", padx=20, pady=(0, 20)
        )
        ctk.CTkLabel(self.sidebar, text="工作区", font=(FONT_FAMILY, 9), text_color="#807398").grid(
            row=2, column=0, sticky="w", padx=24, pady=(0, 10)
        )

        self._nav_idle_icon: dict[str, ctk.CTkImage] = {}
        self._nav_active_icon: dict[str, ctk.CTkImage] = {}
        self.download_nav = self._nav_button(3, "下载工作台", "载", "download", "download")
        self.reader_nav = self._nav_button(4, "本地阅读", "阅", "reader", "book")
        self.workshop_nav = self._nav_button(5, "图片工坊", "坊", "workshop", "sparkle")

        if self._sidebar_image is not None:
            ctk.CTkLabel(
                self.sidebar,
                text="",
                image=self._sidebar_image,
                fg_color="transparent",
            ).grid(row=7, column=0, sticky="s", pady=(0, 2))

        foot = ctk.CTkFrame(
            self.sidebar, fg_color="#2C2745", corner_radius=16, border_width=1, border_color=SIDEBAR_LINE
        )
        foot.grid(row=8, column=0, sticky="ew", padx=14, pady=(10, 12))
        foot.grid_columnconfigure(1, weight=1)
        folder_icon = self._small_icon("folder", "amber", 18)
        if folder_icon is not None:
            ctk.CTkLabel(foot, text="", image=folder_icon, fg_color="transparent", width=18, height=18).grid(
                row=0, column=0, sticky="w", padx=(13, 6), pady=(12, 0)
            )
        ctk.CTkLabel(foot, text="下载位置", font=(FONT_FAMILY, 9), text_color=SIDEBAR_MUTED).grid(
            row=0, column=1, sticky="w", pady=(11, 0)
        )
        ctk.CTkButton(
            foot,
            text="更改",
            width=40,
            height=22,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#3A3153",
            text_color="#C9A7BC",
            font=(FONT_FAMILY, 9),
            command=self._choose_output,
        ).grid(row=0, column=2, sticky="e", padx=(4, 10), pady=(10, 0))
        self.sidebar_output = ctk.CTkLabel(
            foot,
            text=self._short_path(self.output.get()),
            font=(FONT_FAMILY, 10),
            text_color="#EAE5F5",
            wraplength=178,
            justify="left",
            anchor="w",
        )
        self.sidebar_output.grid(row=1, column=0, columnspan=3, sticky="w", padx=13, pady=(5, 13))

        ctk.CTkLabel(
            self.sidebar,
            text=f"未来不是未来  ·  v{APP_VERSION}",
            font=(FONT_FAMILY, 8),
            text_color="#6E638A",
        ).grid(row=9, column=0, sticky="w", padx=24, pady=(0, 15))

    def _build_main(self) -> None:
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self.main, fg_color=HERO, corner_radius=24, height=112)
        self.header.grid(row=0, column=0, sticky="ew", padx=30, pady=(22, 14))
        self.header.grid_propagate(False)
        self.header.grid_columnconfigure(0, weight=1)

        if self._hero_image is not None:
            ctk.CTkLabel(
                self.header,
                text="",
                image=self._hero_image,
                fg_color="transparent",
            ).place(relx=1.0, rely=0.5, anchor="e", x=18)

        head_left = ctk.CTkFrame(self.header, fg_color="transparent")
        head_left.grid(row=0, column=0, sticky="w", padx=(26, 0), pady=(14, 12))
        self.eyebrow = ctk.CTkLabel(
            head_left,
            text="FUTURE REALM · DOWNLOAD",
            font=(FONT_FAMILY, 9, "bold"),
            text_color="#C9A6D8",
        )
        self.eyebrow.grid(row=0, column=0, sticky="w")
        self.heading = ctk.CTkLabel(head_left, text="下载工作台", font=(FONT_FAMILY, 26, "bold"), text_color=HERO_TEXT)
        self.heading.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.subheading = ctk.CTkLabel(
            head_left,
            text="整理任务，安心下载，随时继续阅读。",
            font=(FONT_FAMILY, 10),
            text_color=HERO_MUTED,
        )
        self.subheading.grid(row=2, column=0, sticky="w", pady=(3, 0))
        self.local_chip = ctk.CTkLabel(
            head_left,
            text="本地保存 · 不上传 · 无需登录",
            font=(FONT_FAMILY, 9),
            text_color=HERO_FAINT,
        )
        self.local_chip.grid(row=3, column=0, sticky="w", pady=(5, 0))

        self.status_pill = ctk.CTkLabel(
            self.header,
            text="●  就绪",
            width=122,
            height=34,
            fg_color=HERO_SOFT,
            text_color="#F4C9DB",
            corner_radius=17,
            font=(FONT_FAMILY, 10),
        )
        self.status_pill.place(relx=1.0, x=-24, y=17, anchor="ne")

        self.page_stack = ctk.CTkFrame(self.main, fg_color="transparent")
        self.page_stack.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 18))
        self.page_stack.grid_columnconfigure(0, weight=1)
        self.page_stack.grid_rowconfigure(0, weight=1)
        self.download_page = ctk.CTkFrame(self.page_stack, fg_color="transparent")
        self.reader_page = ctk.CTkFrame(self.page_stack, fg_color="transparent")
        self.workshop_page = ctk.CTkFrame(self.page_stack, fg_color="transparent")
        self.download_page.place(x=0, y=0, relwidth=1, relheight=1)
        self.reader_page.place_forget()
        self.workshop_page.place_forget()
        self._build_download_page()
        self._build_reader_page()
        self._build_workshop_page()

    def _build_download_page(self) -> None:
        page = self.download_page
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(2, weight=1)

        task = self._card(
            page,
            "创建下载任务",
            "输入编号后开始；批量任务会按顺序处理。",
            icon="download",
            tone="rose",
        )
        task.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 14))
        task.grid_columnconfigure(0, weight=1)

        self.mode_picker = PillSwitch(task, ["单本下载", "批量范围"], self.mode, self._change_mode)
        self.mode_picker.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 16))

        self.single_box = ctk.CTkFrame(task, fg_color="transparent")
        self.single_box.grid(row=3, column=0, sticky="ew", padx=22)
        self.single_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.single_box, text="漫画编号", font=(FONT_FAMILY, 10), text_color=TEXT_SOFT).grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        self.single_entry = ctk.CTkEntry(
            self.single_box,
            placeholder_text="输入编号，例如 123456",
            height=46,
            corner_radius=12,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT,
            placeholder_text_color=FAINT,
            font=(FONT_FAMILY, 12),
        )
        self.single_entry.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        polish_entry(self.single_entry)

        self.range_box = ctk.CTkFrame(task, fg_color="transparent")
        self.range_box.grid(row=3, column=0, sticky="ew", padx=22)
        self.range_box.grid_columnconfigure(0, weight=1)
        self.range_box.grid_columnconfigure(1, weight=1)
        self.range_start = self._entry(self.range_box, "起始编号", "例如 100000", row=0, column=0)
        self.range_end = self._entry(self.range_box, "结束编号", "例如 100050", row=0, column=1, left_pad=10)
        self.range_box.grid_remove()

        path_row = ctk.CTkFrame(task, fg_color="transparent")
        path_row.grid(row=4, column=0, sticky="ew", padx=22, pady=(15, 14))
        path_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(path_row, text="保存到", font=(FONT_FAMILY, 10), text_color=TEXT_SOFT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 7)
        )
        self.output_entry = ctk.CTkEntry(
            path_row,
            textvariable=self.output,
            height=42,
            corner_radius=11,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 10),
        )
        self.output_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        polish_entry(self.output_entry)
        ctk.CTkButton(
            path_row,
            text="选择目录",
            width=94,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 10),
            command=self._choose_output,
        ).grid(row=1, column=1)

        buttons = ctk.CTkFrame(task, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 13))
        buttons.grid_columnconfigure(0, weight=1)
        self.start_button = ctk.CTkButton(
            buttons,
            text="开始下载  →",
            height=46,
            corner_radius=13,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 12),
            command=self._start,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.stop_button = ctk.CTkButton(
            buttons,
            text="停止",
            width=88,
            height=46,
            corner_radius=13,
            fg_color=SURFACE_ALT,
            hover_color="#F7E7ED",
            text_color=DANGER,
            font=(FONT_FAMILY, 10),
            state="disabled",
            command=self._stop,
        )
        self.stop_button.grid(row=0, column=1)

        note = ctk.CTkFrame(task, fg_color=SURFACE_SOFT, corner_radius=12)
        note.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 15))
        note.grid_columnconfigure(1, weight=1)
        note_icon = self._small_icon("folder", "amber", 22)
        if note_icon is not None:
            ctk.CTkLabel(note, text="", image=note_icon, fg_color="transparent", width=22, height=22).grid(
                row=0, column=0, padx=(13, 8), pady=9
            )
        ctk.CTkLabel(
            note,
            text="下载内容保存在本地目录，升级程序不会删除。",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=9)

        side = ctk.CTkFrame(page, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=(0, 14))
        side.grid_columnconfigure(0, weight=1)

        settings = self._card(side, "下载设置", "按你的网络情况调整重试与间隔。", icon="sliders", tone="lilac")
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        settings.grid_columnconfigure(0, weight=1)
        settings.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            settings,
            text="打开目录 ↗",
            width=84,
            height=22,
            corner_radius=7,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color="#7E70A2",
            font=(FONT_FAMILY, 9),
            command=self._open_output_dir,
        ).place(relx=1.0, x=-18, y=14, anchor="ne")
        self.retry_entry = self._entry(settings, "失败重试轮数", "3", row=2, column=0, default="3")
        self.delay_entry = self._entry(settings, "任务间隔（秒）", "1", row=2, column=1, left_pad=8, default="1")
        ctk.CTkLabel(
            settings,
            text="间隔会降低连续请求频率；重试仅针对失败项。",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            wraplength=260,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=22, pady=(7, 16))

        progress_card = self._card(side, "任务进度", "当前任务的处理情况。", icon="chart", tone="amber")
        progress_card.grid(row=1, column=0, sticky="ew")
        progress_card.grid_columnconfigure(0, weight=1)
        count_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        count_row.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 11))
        count_row.grid_columnconfigure(0, weight=1)
        self.progress_count = ctk.CTkLabel(
            count_row, text="0 / 0", font=(FONT_FAMILY, 24, "bold"), text_color=TEXT
        )
        self.progress_count.grid(row=0, column=0, sticky="w")
        self.progress_percent = ctk.CTkLabel(
            count_row, text="0%", font=(FONT_FAMILY, 13, "bold"), text_color=ACCENT
        )
        self.progress_percent.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(count_row, text="已完成 / 总数", font=(FONT_FAMILY, 9), text_color=MUTED).grid(
            row=1, column=0, sticky="w", pady=(1, 0)
        )
        self.progress_bar = ctk.CTkProgressBar(
            progress_card, height=9, corner_radius=6, progress_color=ACCENT, fg_color=SURFACE_ALT
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 10))
        self.progress_text = ctk.CTkLabel(progress_card, text="等待开始", font=(FONT_FAMILY, 9), text_color=MUTED)
        self.progress_text.grid(row=4, column=0, sticky="w", padx=22, pady=(0, 17))

        logs = self._card(page, "运行日志", "进度与错误会显示在这里。", icon="terminal", tone="plum")
        logs.grid(row=2, column=0, columnspan=2, sticky="nsew")
        logs.grid_columnconfigure(0, weight=1)
        logs.grid_rowconfigure(2, weight=1)
        ctk.CTkButton(
            logs,
            text="清空",
            width=56,
            height=26,
            corner_radius=8,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=MUTED,
            font=(FONT_FAMILY, 8),
            command=self._clear_log,
        ).grid(row=0, column=1, sticky="e", padx=(0, 18), pady=(15, 2))
        self.log = ctk.CTkTextbox(
            logs,
            height=40,
            corner_radius=14,
            fg_color=LOG_BG,
            text_color=LOG_TEXT,
            border_width=0,
            font=(FONT_MONO, 10),
            wrap="word",
            scrollbar_button_color="#3C3557",
            scrollbar_button_hover_color=ACCENT_LILAC,
        )
        self.log.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 16))
        for tag, color in (
            ("time", "#8E85A6"),
            ("ok", "#8EDDBE"),
            ("warn", "#F2C98B"),
            ("error", "#FF9DB1"),
            ("accent", "#D8B4FF"),
            ("muted", "#9A90AC"),
        ):
            self.log.tag_config(tag, foreground=color)
        self.log.insert("end", "  ●  ", "accent")
        self.log.insert("end", "等待任务 · 输入漫画编号后点击「开始下载」\n", "muted")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _open_output_dir(self) -> None:
        target = Path(self.output.get()).expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(str(target))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self)

    def _build_reader_page(self) -> None:
        page = self.reader_page
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)
        page.grid_rowconfigure(0, weight=1)

        card = self._card(
            page,
            "本地漫画阅览室",
            "输入已下载漫画的编号，进入连续阅读。",
            icon="book",
            tone="rose",
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(8, weight=1)

        quote = ctk.CTkFrame(card, fg_color=ACCENT_SOFT, corner_radius=16, height=56)
        quote.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 18))
        quote.grid_propagate(False)
        quote.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            quote,
            text="“",
            font=("Georgia", 25, "bold"),
            text_color="#D88FA9",
            width=24,
        ).grid(row=0, column=0, padx=(16, 2), sticky="n")
        ctk.CTkLabel(
            quote,
            text="把喜欢的故事，放进阅读角落",
            font=(FONT_FAMILY, 11),
            text_color="#A45C7A",
        ).grid(row=0, column=1, sticky="w", pady=(17, 0))
        ctk.CTkLabel(
            quote,
            text="❀",
            font=(FONT_FAMILY, 12),
            text_color="#E4B3C6",
        ).grid(row=0, column=2, padx=(0, 16), pady=(15, 0))

        ctk.CTkLabel(card, text="漫画编号", font=(FONT_FAMILY, 10), text_color=TEXT_SOFT).grid(
            row=3, column=0, sticky="w", padx=22, pady=(0, 7)
        )
        self.reader_id = ctk.CTkEntry(
            card,
            placeholder_text="例如 123456",
            height=46,
            corner_radius=12,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT,
            placeholder_text_color=FAINT,
            font=(FONT_FAMILY, 12),
        )
        self.reader_id.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 9))
        polish_entry(self.reader_id)
        self.reader_source_hint = ctk.CTkLabel(
            card,
            text=f"从这里读取：{self.output.get()}",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            wraplength=470,
            justify="left",
            anchor="w",
        )
        self.reader_source_hint.grid(row=5, column=0, sticky="w", padx=22, pady=(0, 17))
        reader_actions = ctk.CTkFrame(card, fg_color="transparent")
        reader_actions.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 4))
        reader_actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            reader_actions,
            text="打开阅读器  →",
            height=44,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 12),
            command=self._open_reader,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.reader_scan_button = ctk.CTkButton(
            reader_actions,
            text="扫描文件夹",
            width=112,
            height=44,
            corner_radius=12,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 10),
            command=self._scan_reader_folder,
        )
        self.reader_scan_button.grid(row=0, column=1)

        tips = ctk.CTkFrame(card, fg_color=SURFACE_SOFT, corner_radius=14, border_width=1, border_color=STROKE)
        tips.grid(row=7, column=0, sticky="ew", padx=22, pady=(15, 0))
        tips.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(tips, text="阅读快捷键", font=(FONT_FAMILY, 9, "bold"), text_color=TEXT_SOFT).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(11, 7)
        )
        for index, (key, description) in enumerate(
            (("滚轮", "连续阅读"), ("Ctrl + / −", "放大 / 缩小"), ("F11 / Esc", "沉浸 / 退出"))
        ):
            ctk.CTkLabel(
                tips,
                text=key,
                font=(FONT_FAMILY, 8),
                text_color=TEXT_SOFT,
                fg_color=SURFACE,
                corner_radius=7,
                height=22,
                width=86,
            ).grid(row=index + 1, column=0, sticky="w", padx=(15, 9), pady=2)
            ctk.CTkLabel(tips, text=description, font=(FONT_FAMILY, 9), text_color=MUTED, anchor="w").grid(
                row=index + 1, column=1, sticky="w", pady=2
            )
        ctk.CTkLabel(tips, text="", height=7).grid(row=4, column=0, columnspan=2)

        if self._nook_image is not None:
            ctk.CTkLabel(
                card,
                text="",
                image=self._nook_image,
                fg_color="transparent",
            ).grid(row=9, column=0, sticky="s", pady=(4, 16))

        scan_card = self._card(
            page,
            "扫描漫画文件夹",
            "列出图片文件和含图片的子文件夹；进入文件夹后可查看图片名。扫描不会递归解码整个漫画库。",
            icon="search",
            tone="plum",
        )
        scan_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        scan_card.grid_columnconfigure(0, weight=1)
        scan_card.grid_rowconfigure(4, weight=1)
        self.reader_scan_count = ctk.CTkLabel(
            scan_card,
            text="0 项",
            font=(FONT_FAMILY, 8),
            text_color="#7E6FA3",
            fg_color=LILAC_SOFT,
            corner_radius=8,
            height=22,
        )
        self.reader_scan_count.place(relx=1.0, x=-20, y=18, anchor="ne")

        scan_status_row = ctk.CTkFrame(scan_card, fg_color="transparent")
        scan_status_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        scan_status_row.grid_columnconfigure(0, weight=1)
        self.reader_scan_status = ctk.CTkLabel(
            scan_status_row, text="尚未扫描", font=(FONT_FAMILY, 9), text_color=MUTED, anchor="w"
        )
        self.reader_scan_status.grid(row=0, column=0, sticky="ew")
        self.reader_scan_parent_button = ctk.CTkButton(
            scan_status_row,
            text="返回上级",
            width=78,
            height=28,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 8),
            command=self._reader_scan_parent,
            state="disabled",
        )
        self.reader_scan_parent_button.grid(row=0, column=1, padx=(8, 0))
        self.reader_scan_search = ctk.CTkEntry(
            scan_card,
            placeholder_text="搜索图片文件名或文件夹名",
            height=38,
            corner_radius=11,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT,
            placeholder_text_color=FAINT,
            font=(FONT_FAMILY, 10),
        )
        self.reader_scan_search.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        polish_entry(self.reader_scan_search)
        self.reader_scan_search.bind("<KeyRelease>", self._filter_reader_scan, add="+")

        list_shell = ctk.CTkFrame(
            scan_card, fg_color=SURFACE_SOFT, corner_radius=14, border_width=1, border_color=STROKE
        )
        list_shell.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 12))
        list_shell.grid_columnconfigure(0, weight=1)
        list_shell.grid_rowconfigure(0, weight=1)
        self.reader_scan_list = tk.Listbox(
            list_shell,
            height=12,
            font=(FONT_FAMILY, 10),
            fg=TEXT,
            bg=SURFACE_SOFT,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            selectborderwidth=0,
            activestyle="none",
            exportselection=False,
        )
        self.reader_scan_list.grid(row=0, column=0, sticky="nsew", padx=(11, 5), pady=9)
        self.reader_scan_empty = ctk.CTkLabel(
            list_shell,
            text="尚未扫描\n点击「扫描文件夹」选择一个漫画库\n\n支持 JPG · PNG · WEBP · GIF",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            fg_color=SURFACE_SOFT,
            justify="center",
            image=self._scan_empty_image,
            compound="top",
        )
        self.reader_scan_empty.place(relx=0.5, rely=0.5, anchor="center")
        reader_scan_scroll = ctk.CTkScrollbar(
            list_shell,
            command=self.reader_scan_list.yview,
            width=10,
            fg_color="transparent",
            button_color="#D9CFE2",
            button_hover_color=ACCENT_LILAC,
        )
        reader_scan_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=8)
        self.reader_scan_list.configure(yscrollcommand=reader_scan_scroll.set)
        self.reader_scan_list.bind("<Double-Button-1>", lambda _event: self._activate_reader_scan_item(), add="+")
        ctk.CTkButton(
            scan_card,
            text="进入文件夹 / 打开图片  →",
            height=42,
            corner_radius=12,
            fg_color=ACCENT_LILAC,
            hover_color=ACCENT_LILAC_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 10),
            command=self._activate_reader_scan_item,
        ).grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 18))

    def _build_workshop_page(self) -> None:
        page = self.workshop_page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        content = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_fg_color="transparent",
            scrollbar_button_color="#D8D0EA",
            scrollbar_button_hover_color=ACCENT_LILAC,
        )
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)

        intro = ctk.CTkFrame(content, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=STROKE)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        intro.grid_columnconfigure(1, weight=1)
        intro_icon = self._small_icon("sparkle", "mint", 26)
        if intro_icon is not None:
            ctk.CTkLabel(intro, text="", image=intro_icon, fg_color="transparent", width=26, height=26).grid(
                row=0, column=0, rowspan=2, padx=(16, 10), pady=10
            )
        ctk.CTkLabel(
            intro,
            text="本地处理 · 图片不会上传",
            font=(FONT_FAMILY, 10, "bold"),
            text_color=TEXT_SOFT,
            anchor="w",
        ).grid(row=0, column=1, sticky="sw", pady=(10, 0))
        ctk.CTkLabel(
            intro,
            text="混淆、光棱与 ZIP 图片伪装都在本机完成。",
            font=(FONT_FAMILY, 8),
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="nw", pady=(2, 10))
        ctk.CTkLabel(
            intro,
            text="无需联网",
            font=(FONT_FAMILY, 8),
            text_color="#6C8F82",
            fg_color="#EAF5F0",
            corner_radius=8,
            height=22,
        ).grid(row=0, column=2, rowspan=2, padx=(10, 16))

        preview_card = self._card(
            content,
            "图片混淆",
            "Gilbert 曲线与黄金比例偏移 · 和手机版使用相同算法",
            icon="image",
            tone="lilac",
        )
        preview_card.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 14))
        preview_card.grid_columnconfigure(0, weight=1)
        obf_empty = None
        if ui_art is not None:
            empty_art = ui_art.card_icon("image", "lilac", 92)
            self._obf_empty_image = ctk.CTkImage(light_image=empty_art, dark_image=empty_art, size=(92, 92))
            obf_empty = self._obf_empty_image
        self.obf_preview_label = ctk.CTkLabel(
            preview_card,
            text="尚未选择图片\n从电脑选择一张图片开始 · 建议 PNG",
            image=obf_empty,
            compound="top",
            height=300,
            fg_color="#F7F1FA",
            corner_radius=18,
            text_color=MUTED,
            font=(FONT_FAMILY, 10),
            justify="center",
        )
        self.obf_preview_label.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))
        self.obf_info = ctk.CTkLabel(
            preview_card,
            text="建议使用 PNG；超大图片会缩小到 800 万像素 / 4000 px 长边以内。",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            wraplength=480,
            justify="left",
            anchor="w",
        )
        self.obf_info.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 14))
        self.obf_pick_button = ctk.CTkButton(
            preview_card,
            text="选择图片",
            height=42,
            corner_radius=12,
            fg_color=ACCENT_LILAC,
            hover_color=ACCENT_LILAC_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 11),
            command=self._choose_obfuscation_image,
        )
        self.obf_pick_button.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 18))

        controls = self._card(
            content,
            "处理控制",
            "混淆后按相同轮数解混淆；保存 PNG 保持像素不变。",
            icon="sliders",
            tone="rose",
        )
        controls.grid(row=1, column=1, sticky="nsew", padx=(12, 0), pady=(0, 14))
        controls.grid_columnconfigure(0, weight=1)
        self.obf_mode_picker = PillSwitch(controls, ["混淆", "解混淆"], self.obf_mode, height=40)
        self.obf_mode_picker.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        ctk.CTkLabel(controls, text="处理轮数（1–10）", font=(FONT_FAMILY, 10), text_color=TEXT_SOFT).grid(
            row=3, column=0, sticky="w", padx=20, pady=(0, 7)
        )
        rounds_row = ctk.CTkFrame(controls, fg_color="transparent")
        rounds_row.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 14))
        rounds_row.grid_columnconfigure(1, weight=1)
        self.obf_minus_button = ctk.CTkButton(
            rounds_row,
            text="−",
            width=40,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 14),
            command=lambda: self._adjust_obf_rounds(-1),
        )
        self.obf_minus_button.grid(row=0, column=0, padx=(0, 7))
        self.obf_rounds_entry = ctk.CTkEntry(
            rounds_row,
            height=42,
            corner_radius=11,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT,
            justify="center",
            font=(FONT_FAMILY, 12),
        )
        self.obf_rounds_entry.insert(0, "1")
        self.obf_rounds_entry.grid(row=0, column=1, sticky="ew")
        polish_entry(self.obf_rounds_entry)
        self.obf_plus_button = ctk.CTkButton(
            rounds_row,
            text="+",
            width=40,
            height=42,
            corner_radius=11,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 14),
            command=lambda: self._adjust_obf_rounds(1),
        )
        self.obf_plus_button.grid(row=0, column=2, padx=(7, 0))
        self.obf_run_button = ctk.CTkButton(
            controls,
            text="开始混淆  →",
            height=44,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 12),
            command=self._start_obfuscation,
        )
        self.obf_run_button.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 9))
        action_row = ctk.CTkFrame(controls, fg_color="transparent")
        action_row.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 12))
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)
        self.obf_restore_button = ctk.CTkButton(
            action_row,
            text="还原原图",
            height=38,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 10),
            command=self._restore_obfuscation_source,
        )
        self.obf_restore_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.obf_save_button = ctk.CTkButton(
            action_row,
            text="保存 PNG",
            height=38,
            corner_radius=10,
            fg_color=SURFACE_ALT,
            hover_color=LILAC_SOFT,
            text_color=TEXT_SOFT,
            font=(FONT_FAMILY, 10),
            command=self._save_obfuscation_result,
        )
        self.obf_save_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.obf_progress = ctk.CTkProgressBar(
            controls, height=6, corner_radius=4, progress_color=ACCENT_LILAC, fg_color=SURFACE_ALT
        )
        self.obf_progress.set(0)
        self.obf_progress.grid(row=7, column=0, sticky="ew", padx=20, pady=(2, 8))
        self.obf_status = ctk.CTkLabel(controls, text="等待选择图片", font=(FONT_FAMILY, 9), text_color=MUTED)
        self.obf_status.grid(row=8, column=0, sticky="w", padx=20, pady=(0, 16))
        tips_box = ctk.CTkFrame(controls, fg_color=SURFACE_SOFT, corner_radius=12, border_width=1, border_color=STROKE)
        tips_box.grid(row=9, column=0, sticky="ew", padx=20, pady=(0, 18))
        for line_index, line in enumerate(
            (
                "每轮都会按 Gilbert 曲线重排全部像素",
                "解混淆请使用与混淆时相同的轮数",
                "保存为 PNG 可以保持像素完全可逆",
            )
        ):
            ctk.CTkLabel(
                tips_box,
                text=f"·   {line}",
                font=(FONT_FAMILY, 9),
                text_color=MUTED,
                anchor="w",
            ).pack(anchor="w", padx=14, pady=(9 if line_index == 0 else 3, 9 if line_index == 2 else 0))

        tool_row = ctk.CTkFrame(content, fg_color="transparent")
        tool_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        tool_row.grid_columnconfigure(0, weight=1)
        tool_row.grid_columnconfigure(1, weight=1)

        prism = ctk.CTkFrame(tool_row, fg_color=HERO, corner_radius=22, border_width=1, border_color=HERO_LINE)
        prism.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        prism.grid_columnconfigure(1, weight=1)
        prism_icon = self._small_icon("sparkle", "lilac", 34)
        if prism_icon is not None:
            ctk.CTkLabel(prism, text="", image=prism_icon, fg_color="transparent", width=34, height=34).grid(
                row=0, column=0, rowspan=2, padx=(22, 11), pady=(18, 0), sticky="n"
            )
        ctk.CTkLabel(prism, text="光棱工厂", font=(FONT_FAMILY, 15, "bold"), text_color=HERO_TEXT).grid(
            row=0, column=1, sticky="sw", padx=(0, 22), pady=(18, 0)
        )
        ctk.CTkLabel(
            prism,
            text="双图融合和显形 · 打开本地离线页面",
            font=(FONT_FAMILY, 9),
            text_color=HERO_MUTED,
        ).grid(row=1, column=1, sticky="nw", padx=(0, 22), pady=(2, 0))
        ctk.CTkLabel(
            prism,
            text="与手机版使用同一套光棱工厂页面。页面在默认浏览器中离线打开。",
            font=(FONT_FAMILY, 9),
            text_color=HERO_FAINT,
            wraplength=290,
            justify="left",
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=22, pady=(12, 12))
        ctk.CTkButton(
            prism,
            text="打开光棱工厂  ↗",
            height=40,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 10),
            command=self._open_prism_factory,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 18))

        hidden = self._card(
            tool_row,
            "图片隐藏 ZIP",
            "把一个 ZIP 附加到 JPG/PNG 文件末尾",
            icon="folder",
            tone="amber",
        )
        hidden.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        hidden.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hidden,
            text="导出结果仍可作为普通图片查看。此功能只做伪装，不加密，也不提供提取入口。",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            wraplength=280,
            justify="left",
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=22, pady=(0, 12))
        self.hidden_pack_button = ctk.CTkButton(
            hidden,
            text="制作图片隐藏 ZIP  →",
            height=40,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=(FONT_FAMILY, 10),
            command=self._create_hidden_zip_image,
        )
        self.hidden_pack_button.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        self.hidden_progress = ctk.CTkProgressBar(
            hidden, height=5, corner_radius=4, progress_color=ACCENT, fg_color=SURFACE_ALT
        )
        self.hidden_progress.set(0)
        self.hidden_progress.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 5))
        self.hidden_status = ctk.CTkLabel(hidden, text="未开始", font=(FONT_FAMILY, 9), text_color=MUTED)
        self.hidden_status.grid(row=5, column=0, sticky="w", padx=22, pady=(0, 16))

        about = self._card(content, "关于我", "未来不是未来 · 未来漫境", icon="heart", tone="rose")
        about.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        about.grid_columnconfigure(0, weight=3)
        about.grid_columnconfigure(1, weight=2)
        ctk.CTkLabel(
            about,
            text="漫画收藏、连续阅读和图片创作放在一个轻巧的小空间。图片工具在本机处理，处理结果由你决定保存位置。",
            font=(FONT_FAMILY, 9),
            text_color=MUTED,
            wraplength=560,
            justify="left",
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=22, pady=(0, 14))
        sources = ctk.CTkFrame(about, fg_color="transparent")
        sources.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 18))
        sources.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            sources, text="模块来源 · 点击项目名打开 GitHub", font=(FONT_FAMILY, 9), text_color=TEXT_SOFT
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        source_rows = (
            ("漫画下载（Windows）", "hect0x7/JMComic-Crawler-Python", "https://github.com/hect0x7/JMComic-Crawler-Python"),
            ("光棱工厂", "TankFactory/Mirage_Decode", "https://github.com/TankFactory/Mirage_Decode"),
            ("图片混淆曲线", "jakubcerveny/gilbert", "https://github.com/jakubcerveny/gilbert"),
        )
        for row, (module, repository, url) in enumerate(source_rows, start=1):
            ctk.CTkLabel(
                sources, text=module, font=(FONT_FAMILY, 9), text_color=MUTED, anchor="w"
            ).grid(row=row, column=0, sticky="w", pady=1)
            ctk.CTkButton(
                sources,
                text=f"{repository}  ↗",
                height=26,
                corner_radius=8,
                fg_color="transparent",
                hover_color=LILAC_SOFT,
                text_color="#7166B5",
                font=(FONT_FAMILY, 9),
                anchor="w",
                command=lambda address=url: webbrowser.open(address),
            ).grid(row=row, column=1, sticky="w", padx=(14, 0), pady=1)

        credit = ctk.CTkFrame(about, fg_color=LILAC_SOFT, corner_radius=16)
        credit.grid(row=2, column=1, rowspan=2, sticky="nsew", padx=(12, 22), pady=(0, 18))
        credit.grid_columnconfigure(1, weight=1)
        if self._about_image is not None:
            ctk.CTkLabel(credit, text="", image=self._about_image, fg_color="transparent").grid(
                row=0, column=0, rowspan=2, padx=(17, 10), pady=(17, 4), sticky="n"
            )
        ctk.CTkLabel(credit, text="未来不是未来", font=(FONT_FAMILY, 14, "bold"), text_color="#3D3760").grid(
            row=0, column=1, sticky="sw", pady=(18, 2), padx=(0, 16)
        )
        ctk.CTkLabel(credit, text="创作者 · 未来漫境", font=(FONT_FAMILY, 9), text_color="#7C76A0").grid(
            row=1, column=1, sticky="nw", pady=(0, 12), padx=(0, 16)
        )
        ctk.CTkFrame(credit, height=1, fg_color="#E2DAF7").grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 10)
        )
        ctk.CTkLabel(credit, text=f"版本  {APP_VERSION}", font=(FONT_FAMILY, 9), text_color="#5A5380").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 6)
        )
        ctk.CTkLabel(credit, text="交流 QQ 群  540306092", font=(FONT_FAMILY, 9), text_color="#5A5380").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 16)
        )

    def _choose_obfuscation_image(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("所有文件", "*.*")],
        )
        if not selected:
            return
        try:
            with Image.open(selected) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGBA")
            width, height = image.size
            scale = min(
                1.0,
                MAX_IMAGE_SIDE / max(width, height),
                math.sqrt(MAX_IMAGE_PIXELS / (width * height)),
            )
            if scale < 1.0:
                size = (max(1, int(width * scale)), max(1, int(height * scale)))
                resized = image.resize(size, Image.Resampling.LANCZOS)
                image.close()
                image = resized
            self.obf_source = image.copy()
            self.obf_current = image
            self.obf_path = Path(selected)
            self.obf_result_tag = "原图"
            self._render_obfuscation_preview()
            self.obf_progress.set(0)
            self.obf_status.configure(text="图片已载入，可以开始混淆或解混淆。", text_color=MUTED)
            self.obf_info.configure(text=f"{self.obf_path.name}  ·  {image.width} × {image.height} px")
            self._update_obfuscation_controls()
        except Exception as exc:
            messagebox.showerror("无法读取图片", str(exc), parent=self)

    def _render_obfuscation_preview(self) -> None:
        if self.obf_current is None:
            return
        preview = self.obf_current.copy()
        preview.thumbnail((500, 330), Image.Resampling.LANCZOS)
        self.obf_photo = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
        self.obf_preview_label.configure(image=self.obf_photo, text="")

    def _start_obfuscation(self) -> None:
        if self.obf_busy:
            return
        if self.obf_current is None or self.obf_path is None:
            messagebox.showinfo("先选图片", "请先选择一张图片。", parent=self)
            return
        try:
            rounds = int(self.obf_rounds_entry.get().strip())
        except ValueError:
            messagebox.showwarning("轮数不正确", "请输入 1 到 10 的整数。", parent=self)
            return
        if not 1 <= rounds <= 10:
            messagebox.showwarning("轮数不正确", "请输入 1 到 10 的整数。", parent=self)
            return
        mode = self.obf_mode.get()
        image = self.obf_current.copy()
        self.obf_busy = True
        self.obf_progress.set(0)
        self.obf_status.configure(text="正在生成像素路径…", text_color=ACCENT_LILAC)
        self._update_obfuscation_controls()
        threading.Thread(
            target=self._obfuscation_worker,
            args=(image, mode, rounds),
            name="FutureRealm-ImageObfuscation",
            daemon=True,
        ).start()

    def _obfuscation_worker(self, image: Image.Image, mode: str, rounds: int) -> None:
        try:
            image = image.convert("RGBA")
            width, height = image.size
            total = width * height
            order = gilbert_order(
                width,
                height,
                lambda count: self.events.put((
                    "obf_progress",
                    5 + int(count * 45 / total),
                    "正在生成像素路径…",
                )),
            )
            offset = math.floor(GOLDEN_OFFSET_RATIO * total + 0.5) % total
            step = offset if mode == "混淆" else (total - offset) % total
            pixels = image.load()
            cycles = math.gcd(total, step) if step else 0
            notify_every = max(1, total // 100)
            operations = 0
            for round_index in range(rounds):
                if step:
                    for start in range(cycles):
                        current = start
                        first = order[current]
                        carry = pixels[first % width, first // width]
                        while True:
                            next_index = current + step
                            if next_index >= total:
                                next_index -= total
                            location = order[next_index]
                            x, y = location % width, location // width
                            displaced = pixels[x, y]
                            pixels[x, y] = carry
                            carry = displaced
                            current = next_index
                            operations += 1
                            if operations % notify_every == 0 or operations == total * (round_index + 1):
                                within = (operations - total * round_index) / total
                                percent = 50 + int(((round_index + within) / rounds) * 50)
                                self.events.put(("obf_progress", percent, "正在重排像素…"))
                            if current == start:
                                break
                else:
                    self.events.put(("obf_progress", 50 + int((round_index + 1) * 50 / rounds), "像素排列无需变化…"))
            self.events.put(("obf_done", image, mode, rounds))
        except Exception as exc:
            self.events.put(("obf_error", str(exc)))

    def _restore_obfuscation_source(self) -> None:
        if self.obf_busy:
            return
        if self.obf_source is None:
            messagebox.showinfo("先选图片", "请先选择一张图片。", parent=self)
            return
        self.obf_current = self.obf_source.copy()
        self.obf_result_tag = "原图"
        self._render_obfuscation_preview()
        self.obf_progress.set(0)
        self.obf_status.configure(text="已恢复本次载入的原图。", text_color="#4F967B")
        self._update_obfuscation_controls()

    def _save_obfuscation_result(self) -> None:
        if self.obf_busy:
            return
        if self.obf_current is None or self.obf_path is None:
            messagebox.showinfo("先选图片", "请先选择或处理一张图片。", parent=self)
            return
        initial = f"{self.obf_path.stem}-{self.obf_result_tag}.png"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="保存 PNG 图片",
            initialdir=str(self.obf_path.parent),
            initialfile=initial,
            defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")],
        )
        if not destination:
            return
        image = self.obf_current.copy()
        self.obf_busy = True
        self.obf_status.configure(text="正在保存 PNG…", text_color=ACCENT_LILAC)
        self.obf_progress.set(0.5)
        self._update_obfuscation_controls()
        threading.Thread(
            target=self._obfuscation_save_worker,
            args=(image, Path(destination)),
            name="FutureRealm-ImageSave",
            daemon=True,
        ).start()

    def _obfuscation_save_worker(self, image: Image.Image, destination: Path) -> None:
        try:
            image.save(destination, format="PNG", optimize=False)
            self.events.put(("obf_saved", str(destination)))
        except Exception as exc:
            self.events.put(("obf_error", str(exc)))

    def _update_obfuscation_controls(self) -> None:
        state = "disabled" if self.obf_busy else "normal"
        for control in (
            self.obf_pick_button,
            self.obf_mode_picker,
            self.obf_rounds_entry,
            self.obf_minus_button,
            self.obf_plus_button,
            self.obf_run_button,
            self.obf_restore_button,
            self.obf_save_button,
        ):
            control.configure(state=state)

    def _adjust_obf_rounds(self, delta: int) -> None:
        try:
            value = int(self.obf_rounds_entry.get().strip())
        except ValueError:
            value = 1
        value = max(1, min(10, value + delta))
        self.obf_rounds_entry.delete(0, "end")
        self.obf_rounds_entry.insert(0, str(value))

    def _open_prism_factory(self) -> None:
        source = resource_path("prism-factory.html")
        if not source.is_file():
            messagebox.showerror("页面缺失", "找不到随应用提供的光棱工厂离线页面。", parent=self)
            return
        destination = Path(tempfile.gettempdir()) / "未来漫境" / "光棱工厂.html"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if not webbrowser.open(destination.as_uri(), new=2):
                messagebox.showwarning("浏览器未打开", f"可以手动打开这个离线页面：\n{destination}", parent=self)
        except Exception as exc:
            messagebox.showerror("无法打开", str(exc), parent=self)

    def _create_hidden_zip_image(self) -> None:
        if self.hidden_busy:
            return
        image_path = filedialog.askopenfilename(
            parent=self,
            title="选择外层 JPG 或 PNG 图片",
            filetypes=[("JPG/PNG 图片", "*.jpg *.jpeg *.png"), ("所有文件", "*.*")],
        )
        if not image_path:
            return
        zip_path = filedialog.askopenfilename(
            parent=self,
            title="选择要附加的 ZIP 文件",
            filetypes=[("ZIP 文件", "*.zip"), ("所有文件", "*.*")],
        )
        if not zip_path:
            return
        source = Path(image_path)
        archive = Path(zip_path)
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="保存图片隐藏 ZIP",
            initialdir=str(source.parent),
            initialfile=f"{source.stem}-隐藏ZIP{source.suffix}",
            defaultextension=source.suffix,
            filetypes=[("与外层图片相同的格式", f"*{source.suffix}"), ("所有文件", "*.*")],
        )
        if not destination:
            return
        output = Path(destination)
        try:
            if output.resolve() in {source.resolve(), archive.resolve()}:
                messagebox.showwarning("不能覆盖源文件", "请选择新的输出文件名。", parent=self)
                return
        except OSError:
            pass
        self.hidden_busy = True
        self.hidden_pack_button.configure(state="disabled", text="正在制作…")
        self.hidden_progress.set(0)
        self.hidden_status.configure(text="正在附加 ZIP 数据…", text_color=ACCENT_LILAC)
        threading.Thread(
            target=self._hidden_zip_worker,
            args=(source, archive, output),
            name="FutureRealm-HiddenZip",
            daemon=True,
        ).start()

    def _hidden_zip_worker(self, source: Path, archive: Path, output: Path) -> None:
        total = source.stat().st_size + archive.stat().st_size
        copied = 0
        try:
            with output.open("wb") as out:
                for path in (source, archive):
                    with path.open("rb") as inp:
                        while True:
                            chunk = inp.read(1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                            copied += len(chunk)
                            self.events.put(("hidden_progress", copied / total if total else 1.0))
            self.events.put(("hidden_done", str(output)))
        except Exception as exc:
            self.events.put(("hidden_error", str(exc)))

    def _entry(
        self,
        parent,
        label: str,
        placeholder: str,
        *,
        row: int,
        column: int,
        left_pad: int = 0,
        default: str | None = None,
    ) -> ctk.CTkEntry:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        left = 22 if column == 0 else 8
        right = 8 if column == 0 else 22
        block.grid(row=row, column=column, sticky="ew", padx=(left, right), pady=(0, 4))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text=label, font=(FONT_FAMILY, 10), text_color=TEXT_SOFT).grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        entry = ctk.CTkEntry(
            block,
            placeholder_text=placeholder,
            height=42,
            corner_radius=11,
            fg_color=INPUT_BG,
            border_color=INPUT_STROKE,
            text_color=TEXT,
            placeholder_text_color=FAINT,
            font=(FONT_FAMILY, 10),
        )
        entry.grid(row=1, column=0, sticky="ew")
        polish_entry(entry)
        if default is not None:
            entry.insert(0, default)
        return entry

    def show_page(self, name: str, *, animate: bool = True) -> None:
        pages = {
            "download": self.download_page,
            "reader": self.reader_page,
            "workshop": self.workshop_page,
        }
        if name not in pages:
            return
        self.page_name = name
        target = pages[name]
        headings = {
            "download": ("下载工作台", "输入编号创建下载任务，完成后即可在本地阅读。"),
            "reader": ("本地阅读", "把喜欢的故事收进阅读角落，连续阅读更舒服。"),
            "workshop": ("图片工坊", "混淆、光棱和 ZIP 图片伪装都在本地完成。"),
        }
        eyebrows = {
            "download": "FUTURE REALM · DOWNLOAD",
            "reader": "FUTURE REALM · READING",
            "workshop": "FUTURE REALM · STUDIO",
        }
        self.heading.configure(text=headings[name][0])
        self.subheading.configure(text=headings[name][1])
        self.eyebrow.configure(text=eyebrows[name])
        navs = {
            "download": self.download_nav,
            "reader": self.reader_nav,
            "workshop": self.workshop_nav,
        }
        for page_name, nav in navs.items():
            selected = page_name == name
            nav.configure(
                fg_color=SIDEBAR_ACTIVE if selected else "transparent",
                text_color="#FFFFFF" if selected else SIDEBAR_TEXT,
                image=self._nav_active_icon[page_name] if selected else self._nav_idle_icon[page_name],
            )
            bar = self._nav_bars.get(page_name)
            if bar is not None:
                if selected:
                    bar.place(x=3, y=13)
                else:
                    bar.place_forget()

        if self._page_transition_job is not None:
            try:
                self.after_cancel(self._page_transition_job)
            except Exception:
                pass
            self._page_transition_job = None
            settled_name = self._page_transition_target or self._visible_page
            self._page_transition_target = None
            if settled_name in pages:
                for page in pages.values():
                    page.place_forget()
                settled_page = pages[settled_name]
                settled_page.place(x=0, y=0, relwidth=1, relheight=1)
                settled_page.lift()
                self._visible_page = settled_name

        old_name = self._visible_page
        if old_name is None or old_name == name or not animate:
            for page_name, page in pages.items():
                if page_name != name:
                    page.place_forget()
            target.place(x=0, y=0, relwidth=1, relheight=1)
            target.lift()
            self._visible_page = name
            return

        old_page = pages.get(old_name)
        if old_page is None:
            target.place(x=0, y=0, relwidth=1, relheight=1)
            target.lift()
            self._visible_page = name
            return
        page_order = ("download", "reader", "workshop")
        travel = 34 if page_order.index(name) > page_order.index(old_name) else -34
        target.place(x=travel, y=0, relwidth=1, relheight=1)
        target.lift()
        self._page_transition_target = name
        self._page_transition_token += 1
        token = self._page_transition_token
        started = time.perf_counter()
        duration = 0.24

        def animate_step() -> None:
            if token != self._page_transition_token or not self.winfo_exists():
                return
            progress = min(1.0, (time.perf_counter() - started) / duration)
            eased = 1.0 - (1.0 - progress) ** 3
            target.place_configure(x=round(travel * (1.0 - eased)))
            old_page.place_configure(x=round(-travel * eased))
            if progress >= 1.0:
                old_page.place_forget()
                target.place_configure(x=0)
                self._visible_page = name
                self._page_transition_target = None
                self._page_transition_job = None
                return
            self._page_transition_job = self.after(16, animate_step)

        animate_step()

    def _change_mode(self, value: str) -> None:
        if value == "批量范围":
            self.single_box.grid_remove()
            self.range_box.grid()
        else:
            self.range_box.grid_remove()
            self.single_box.grid()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output.get() or str(app_directory()))
        if selected:
            self.output.set(selected)
            self.sidebar_output.configure(text=self._short_path(selected))
            self.reader_source_hint.configure(text=f"从这里读取：{selected}")

    def _start(self) -> None:
        if self.running:
            return
        if self.mode.get() == "单本下载":
            ids = re.findall(r"\d+", self.single_entry.get())
        else:
            try:
                first = int(self.range_start.get().strip())
                last = int(self.range_end.get().strip())
                if first < 0 or last < first:
                    raise ValueError
                total = last - first + 1
                if total > 500 and not messagebox.askyesno(
                    "确认批量任务",
                    f"这个范围包含 {total:,} 个编号，可能持续很久并产生大量请求。仍要继续吗？",
                    parent=self,
                ):
                    return
                ids = [str(value) for value in range(first, last + 1)]
            except ValueError:
                messagebox.showwarning("编号范围无效", "请填写有效的起止编号，并确保结束编号不小于起始编号。", parent=self)
                return
        if not ids:
            messagebox.showwarning("缺少编号", "先输入一个漫画编号，或填写批量编号范围。", parent=self)
            return
        try:
            retries = max(1, int(self.retry_entry.get().strip()))
            delay = max(0.0, float(self.delay_entry.get().strip()))
        except ValueError:
            messagebox.showwarning("设置无效", "重试轮数请输入正整数，间隔请输入不小于 0 的数字。", parent=self)
            return

        out = Path(self.output.get()).expanduser()
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("无法创建保存目录", str(exc), parent=self)
            return

        self.running = True
        self.total = len(ids)
        self.completed = 0
        self.current_id = ""
        self.stop_event.clear()
        self.progress_bar.set(0)
        self.progress_count.configure(text=f"0 / {self.total:,}")
        self.progress_percent.configure(text="0%")
        self.progress_text.configure(text="准备开始…")
        self.status_pill.configure(text="●  正在运行", fg_color="#3B3358", text_color="#CFC0FF")
        self.start_button.configure(state="disabled", text="任务进行中")
        self.stop_button.configure(state="normal")
        self._log(f"开始任务：{len(ids):,} 个编号 · 保存到 {out}")
        threading.Thread(target=self._worker, args=(ids, out, retries, delay), daemon=True).start()

    def _worker(self, ids: list[str], out: Path, retries: int, delay: float) -> None:
        failed: list[str] = []
        finished = 0
        try:
            config_path = out / "option.yml"
            if not config_path.exists():
                config_path.write_text(
                    "download:\n  image:\n    suffix: .jpg\ndir_rule:\n  rule: Bd_Aid\n  base_dir: "
                    + out.as_posix()
                    + "\n",
                    encoding="utf-8",
                )

            for position, comic_id in enumerate(ids, start=1):
                if self.stop_event.is_set():
                    break
                target = out / comic_id
                if any(path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS for path in target.rglob("*")):
                    self.events.put(("log", f"[{position}/{len(ids)}] {comic_id} 已存在，跳过"))
                    finished += 1
                    self.events.put(("progress", finished, len(ids), comic_id))
                    continue

                succeeded = False
                for attempt in range(1, retries + 1):
                    if self.stop_event.is_set():
                        break
                    try:
                        jmcomic.download_album(comic_id, jmcomic.JmOption.from_file(str(config_path)))
                        if not any(
                            path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                            for path in target.rglob("*")
                        ):
                            raise RuntimeError("下载结束后没有找到图片文件")
                        succeeded = True
                        self.events.put(("log", f"[{position}/{len(ids)}] {comic_id} 下载完成"))
                        break
                    except Exception as exc:
                        self.events.put(("log", f"[{position}/{len(ids)}] {comic_id} 第 {attempt} 轮失败：{exc}"))
                        if attempt < retries and not self.stop_event.is_set():
                            time.sleep(min(10, attempt * 2))
                if not succeeded:
                    failed.append(comic_id)
                    self.events.put(("log", f"{comic_id} 加入失败队列"))
                finished += 1
                self.events.put(("progress", finished, len(ids), comic_id))
                if delay and not self.stop_event.is_set():
                    time.sleep(delay)

            round_number = 1
            while failed and round_number <= retries and not self.stop_event.is_set():
                retrying = failed
                failed = []
                self.events.put(("log", f"开始失败队列第 {round_number} 轮，共 {len(retrying)} 个"))
                for index, comic_id in enumerate(retrying):
                    if self.stop_event.is_set():
                        failed.extend(retrying[index:])
                        break
                    try:
                        jmcomic.download_album(comic_id, jmcomic.JmOption.from_file(str(config_path)))
                        target = out / comic_id
                        if not any(
                            path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                            for path in target.rglob("*")
                        ):
                            raise RuntimeError("下载结束后没有找到图片文件")
                        self.events.put(("log", f"{comic_id} 重试成功"))
                    except Exception as exc:
                        failed.append(comic_id)
                        self.events.put(("log", f"{comic_id} 重试失败：{exc}"))
                round_number += 1

            (out / "failed.txt").write_text("\n".join(failed) + ("\n" if failed else ""), encoding="utf-8")
            self.events.put(("done", failed, self.stop_event.is_set(), None))
        except Exception as exc:
            self.events.put(("done", failed, self.stop_event.is_set(), str(exc)))

    def _stop(self) -> None:
        if self.running:
            self.stop_event.set()
            self.stop_button.configure(state="disabled", text="正在停止…")
            self.status_pill.configure(text="●  正在停止", fg_color="#4A3B2E", text_color="#F3D3A2")
            self._log("已请求停止；当前正在进行的单个下载结束后会停止。")

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._log(event[1])
                elif kind == "progress":
                    done, total, comic_id = event[1:]
                    ratio = done / total if total else 0
                    self.progress_bar.set(ratio)
                    self.progress_count.configure(text=f"{done:,} / {total:,}")
                    self.progress_percent.configure(text=f"{round(ratio * 100)}%")
                    self.progress_text.configure(text=f"正在处理编号 {comic_id}")
                elif kind == "obf_progress":
                    percent, text = event[1:]
                    self.obf_progress.set(max(0.0, min(1.0, percent / 100)))
                    self.obf_status.configure(text=f"{text}  {percent}%")
                elif kind == "obf_done":
                    image, mode, rounds = event[1:]
                    self.obf_current = image
                    self.obf_result_tag = mode
                    self.obf_busy = False
                    self._render_obfuscation_preview()
                    self.obf_progress.set(1)
                    self.obf_status.configure(text=f"{mode}完成 · {rounds} 轮", text_color="#4F967B")
                    self.obf_info.configure(
                        text=f"{self.obf_path.name if self.obf_path else '图片'}  ·  {image.width} × {image.height} px  ·  {mode} {rounds} 轮"
                    )
                    self._update_obfuscation_controls()
                elif kind == "obf_saved":
                    self.obf_busy = False
                    self.obf_progress.set(1)
                    self.obf_status.configure(text=f"已保存：{event[1]}", text_color="#4F967B")
                    self._update_obfuscation_controls()
                elif kind == "obf_error":
                    self.obf_busy = False
                    self.obf_progress.set(0)
                    self.obf_status.configure(text=f"处理失败：{event[1]}", text_color=DANGER)
                    self._update_obfuscation_controls()
                    messagebox.showerror("图片处理失败", event[1], parent=self)
                elif kind == "hidden_progress":
                    value = max(0.0, min(1.0, event[1]))
                    self.hidden_progress.set(value)
                    self.hidden_status.configure(text=f"正在附加 ZIP 数据… {round(value * 100)}%")
                elif kind == "hidden_done":
                    self.hidden_busy = False
                    self.hidden_pack_button.configure(state="normal", text="制作图片隐藏 ZIP")
                    self.hidden_progress.set(1)
                    self.hidden_status.configure(text=f"已生成：{event[1]}", text_color="#4F967B")
                    messagebox.showinfo("制作完成", f"图片隐藏 ZIP 已保存：\n{event[1]}", parent=self)
                elif kind == "hidden_error":
                    self.hidden_busy = False
                    self.hidden_pack_button.configure(state="normal", text="制作图片隐藏 ZIP")
                    self.hidden_status.configure(text="制作失败", text_color=DANGER)
                    messagebox.showerror("制作失败", event[1], parent=self)
                elif kind == "reader_scan_done":
                    generation, root, results, error = event[1:]
                    if generation != self.reader_scan_generation:
                        continue
                    self.reader_scan_button.configure(state="normal")
                    if error:
                        self.reader_scan_status.configure(text=f"扫描失败：{error}", text_color=DANGER)
                        continue
                    self.reader_scan_current = root
                    self.reader_scan_parent_button.configure(
                        state="normal" if self.reader_scan_root and root != self.reader_scan_root else "disabled"
                    )
                    self.reader_scan_results = results
                    self._filter_reader_scan()
                    image_total = sum(1 for kind, _path, _count in results if kind == "file")
                    folder_total = sum(1 for kind, _path, _count in results if kind == "folder")
                    if results:
                        self.reader_scan_status.configure(
                            text=f"{root}  ·  {image_total:,} 个图片文件，{folder_total:,} 个子文件夹",
                            text_color=MUTED,
                        )
                    else:
                        self.reader_scan_status.configure(
                            text=f"此目录没有图片文件或含图片的子文件夹：{root}", text_color=MUTED
                        )
                elif kind == "done":
                    failed, stopped, error = event[1:]
                    self.running = False
                    self.start_button.configure(state="normal", text="开始下载")
                    self.stop_button.configure(state="disabled", text="停止")
                    if error:
                        self.status_pill.configure(text="●  遇到错误", fg_color="#4A2B3A", text_color="#FFB3C1")
                        self.progress_text.configure(text="任务因错误结束")
                        self._log(f"任务异常结束：{error}")
                    elif stopped:
                        self.status_pill.configure(text="●  已停止", fg_color="#4A3B2E", text_color="#F3D3A2")
                        self.progress_text.configure(text=f"已停止 · 尚有 {len(failed)} 个失败或未完成")
                        self._log("任务已停止。")
                    else:
                        self.status_pill.configure(text="●  已完成", fg_color="#3A2F4A", text_color="#F4C9DB")
                        self.progress_percent.configure(text="100%")
                        self.progress_text.configure(text=f"任务完成 · 失败 {len(failed)} 个")
                        self._log(f"任务完成：失败 {len(failed)} 个；列表已写入 failed.txt。")
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        lowered = message
        if any(word in lowered for word in ("失败", "错误", "异常", "无效")):
            tag = "error"
        elif any(word in lowered for word in ("完成", "成功", "已保存")):
            tag = "ok"
        elif any(word in lowered for word in ("跳过", "停止", "重试")):
            tag = "warn"
        elif message.startswith("开始任务"):
            tag = "accent"
        else:
            tag = None
        self.log.configure(state="normal")
        self.log.insert("end", f"{stamp}  ", "time")
        if tag is None:
            self.log.insert("end", f"{message}\n")
        else:
            self.log.insert("end", f"{message}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")


    def _open_reader(self) -> None:
        comic_id = self.reader_id.get().strip()
        if not comic_id:
            messagebox.showwarning("缺少编号", "请输入已下载漫画的编号。", parent=self)
            return
        folder = Path(self.output.get()).expanduser() / comic_id
        files = image_files(folder)
        if not files:
            messagebox.showwarning("没有找到图片", f"没有在此目录直接找到可阅读的图片：\n{folder}", parent=self)
            return
        ImageReader(self, folder, files)

    def _scan_reader_folder(self) -> None:
        initial = Path(self.output.get()).expanduser()
        if not initial.is_dir():
            initial = app_directory()
        selected = filedialog.askdirectory(initialdir=str(initial), parent=self, title="选择漫画库或漫画文件夹")
        if not selected:
            return
        root = Path(selected)
        self.reader_scan_root = root
        self.reader_scan_current = root
        self._start_reader_scan(root)

    def _start_reader_scan(self, folder: Path) -> None:
        self.reader_scan_generation += 1
        generation = self.reader_scan_generation
        self.reader_scan_current = folder
        self.reader_scan_results = []
        self.reader_scan_visible = []
        self.reader_scan_list.delete(0, "end")
        self.reader_scan_button.configure(state="disabled")
        self.reader_scan_parent_button.configure(
            state="normal" if self.reader_scan_root and folder != self.reader_scan_root else "disabled"
        )
        self.reader_scan_status.configure(text=f"正在扫描：{folder}", text_color=MUTED)
        threading.Thread(
            target=self._scan_reader_candidates,
            args=(folder, generation),
            daemon=True,
            name="FutureRealm-ReaderScan",
        ).start()

    def _reader_scan_parent(self) -> None:
        current = self.reader_scan_current
        root = self.reader_scan_root
        if current is None or root is None or current == root:
            return
        try:
            parent = current.parent
            if parent == current or root not in parent.parents and parent != root:
                return
        except OSError:
            return
        self._start_reader_scan(parent)

    def _scan_reader_candidates(self, folder: Path, generation: int) -> None:
        results: list[tuple[str, Path, int]] = []
        try:
            files: list[Path] = []
            child_folders: list[tuple[Path, int]] = []

            def direct_image_count(path: Path) -> int:
                count = 0
                try:
                    with os.scandir(path) as children:
                        for child in children:
                            try:
                                if child.is_file(follow_symlinks=False) and Path(child.name).suffix.lower() in IMAGE_EXTENSIONS:
                                    count += 1
                            except OSError:
                                continue
                except OSError:
                    return 0
                return count

            with os.scandir(folder) as children:
                for child in children:
                    try:
                        path = Path(child.path)
                        if child.is_file(follow_symlinks=False) and path.suffix.lower() in IMAGE_EXTENSIONS:
                            files.append(path)
                        elif child.is_dir(follow_symlinks=False):
                            count = direct_image_count(path)
                            if count:
                                child_folders.append((path, count))
                    except OSError:
                        continue
            files.sort(key=natural_key)
            child_folders.sort(key=lambda item: natural_key(item[0]))
            results.extend(("file", path, 0) for path in files)
            results.extend(("folder", path, count) for path, count in child_folders)
            self.events.put(("reader_scan_done", generation, folder, results, None))
        except Exception as exc:
            self.events.put(("reader_scan_done", generation, folder, [], str(exc)))

    def _filter_reader_scan(self, _event=None) -> None:
        if not hasattr(self, "reader_scan_list"):
            return
        query = self.reader_scan_search.get().strip().casefold()
        visible = [
            item for item in self.reader_scan_results
            if not query or query in item[1].name.casefold() or query in str(item[1]).casefold()
        ]
        self.reader_scan_visible = visible
        self.reader_scan_list.delete(0, "end")
        labels = [
            (f"▤   {path.name}" if kind == "file" else f"▸   {path.name}   ·   {count:,} 张")
            for kind, path, count in visible
        ]
        if labels:
            self.reader_scan_list.insert("end", *labels)
            for index, (kind, _path, _count) in enumerate(visible):
                self.reader_scan_list.itemconfig(
                    index,
                    foreground=TEXT_SOFT if kind == "file" else TEXT,
                    background="#FFFFFF" if index % 2 == 0 else SURFACE_SOFT,
                )
        self._sync_reader_scan_empty(bool(labels))
        if hasattr(self, "reader_scan_count"):
            self.reader_scan_count.configure(text=f"{len(labels):,} 项")

    def _sync_reader_scan_empty(self, has_items: bool) -> None:
        empty = getattr(self, "reader_scan_empty", None)
        if empty is None:
            return
        if has_items:
            empty.place_forget()
        else:
            empty.place(relx=0.5, rely=0.5, anchor="center")

    def _activate_reader_scan_item(self) -> None:
        selection = self.reader_scan_list.curselection()
        if not selection:
            messagebox.showinfo("选择文件", "请先从扫描结果中选择一个文件夹或图片。", parent=self)
            return
        index = selection[0]
        if index >= len(self.reader_scan_visible):
            return
        kind, path, _count = self.reader_scan_visible[index]
        if kind == "folder":
            self._start_reader_scan(path)
            return
        files = image_files(path.parent)
        if not files:
            messagebox.showwarning("目录已变化", "该图片所在目录中已没有可阅读图片，请重新扫描。", parent=self)
            return
        ImageReader(self, path.parent, files, start_file=path)


if __name__ == "__main__":
    DownloaderApp().mainloop()
