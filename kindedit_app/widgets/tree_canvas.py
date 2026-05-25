from __future__ import annotations

from tkinter import font
import tkinter as tk

from ..config import clamp_font_size, default_tree_font_size
from ..documents.base import TreeNode, refresh_to_root, refresh_tree_states
from ..platforms import is_macos
from ..theme import LIGHT
from .common import SlimScrollbar, WHEEL_SCROLL_UNITS


class JsonTreeCanvas(tk.Frame):
    def __init__(self, master, on_select, on_context, on_font_delta):
        super().__init__(master, bd=0, highlightthickness=0)
        self.on_select = on_select
        self.on_context = on_context
        self.on_font_delta = on_font_delta
        self.palette = LIGHT
        self.tree_font = font.Font(family="Menlo" if is_macos() else "Consolas", size=default_tree_font_size())
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0)
        self.vbar = SlimScrollbar(self, "vertical", self.canvas.yview)
        self.hbar = SlimScrollbar(self, "horizontal", self.canvas.xview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.root_node: TreeNode | None = None
        self.visible: list[TreeNode] = []
        self.selected: TreeNode | None = None
        self.row_h = 28
        self.indent = 24
        self.toggle_boxes: dict[int, tuple[int, int, int, int]] = {}
        self.row_boxes: dict[int, tuple[int, int, int, int]] = {}
        self.bind_events()

    def bind_events(self) -> None:
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<Button-2>", self._right_click)
        self.canvas.bind("<Button-3>", self._right_click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Control-MouseWheel>", self._font_wheel)

    def set_palette(self, palette: dict) -> None:
        self.palette = palette
        self.configure(bg=palette["panel"])
        self.canvas.configure(bg=palette["panel"])
        self.vbar.set_palette(palette)
        self.hbar.set_palette(palette)
        self.draw()

    def set_font_size(self, size: int) -> None:
        self.tree_font.configure(size=clamp_font_size(size))
        self.row_h = max(24, self.tree_font.metrics("linespace") + 10)
        self.draw()

    def set_tree(self, root: TreeNode | None) -> None:
        self.root_node = root
        self.selected = None
        self.draw()

    def flatten(self) -> list[TreeNode]:
        out: list[TreeNode] = []

        def walk(node: TreeNode) -> None:
            out.append(node)
            if node.expanded:
                for child in node.children:
                    walk(child)

        if self.root_node:
            walk(self.root_node)
        return out

    def draw(self) -> None:
        self.canvas.delete("all")
        self.toggle_boxes.clear()
        self.row_boxes.clear()
        self.visible = self.flatten()
        width = max(self.canvas.winfo_width(), 800)
        geometries = []
        icon_boxes: dict[int, tuple[int, int, int, int]] = {}
        icon_pairs = (("{", "}"), ("[", "]"), ("‹", "›"))
        icon_h = max(20, self.tree_font.metrics("linespace") + 2)
        icon_gap = max(1, self.tree_font.measure(" ") // 8)
        icon_w = max(icon_h, max(self._icon_pair_width(pair, icon_gap) for pair in icon_pairs) + 1)
        for idx, node in enumerate(self.visible):
            y = idx * self.row_h
            x = node.depth * self.indent + 8
            icon_pair = ("{", "}") if node.kind == "object" else ("[", "]") if node.kind == "array" else ("‹", "›")
            icon_x = x + 22
            icon_y1 = y + (self.row_h - icon_h) // 2
            icon_box = (icon_x, icon_y1, icon_x + icon_w, icon_y1 + icon_h)
            icon_boxes[id(node)] = icon_box
            geometries.append((idx, node, x, y, icon_pair, icon_gap, icon_w, icon_x, icon_box))
            if node.has_children:
                self.toggle_boxes[idx] = (x, y + 7, x + 14, y + 21)
        max_text_width = width
        for idx, node, x, y, icon_pair, icon_gap, icon_w, icon_x, icon_box in geometries:
            self.row_boxes[idx] = (0, y, width, y + self.row_h)
            if node is self.selected:
                self.canvas.create_rectangle(0, y, width, y + self.row_h, fill=self.palette["select"], width=0)

        for idx, node, x, y, icon_pair, icon_gap, icon_w, icon_x, icon_box in geometries:
            if node.parent is not None:
                parent_box = icon_boxes.get(id(node.parent))
                if parent_box:
                    parent_mid_x = (parent_box[0] + parent_box[2]) // 2
                    parent_bottom_y = parent_box[3]
                    child_mid_y = y + self.row_h // 2
                    child_line_end_x = max(parent_mid_x, icon_x - 6)
                    self._draw_vertical_connector(parent_mid_x, parent_bottom_y, child_mid_y, self.toggle_boxes.values())
                    self.canvas.create_line(parent_mid_x, child_mid_y, child_line_end_x, child_mid_y, fill=self.palette["line"], dash=(2, 3))

        for idx, node, x, y, icon_pair, icon_gap, icon_w, icon_x, icon_box in geometries:
            if node.has_children:
                box = self.toggle_boxes[idx]
                self.canvas.create_rectangle(*box, outline=self.palette["line"], fill=self.palette["panel2"])
                self.canvas.create_line(x + 3, y + 14, x + 11, y + 14, fill=self.palette["text"])
                if not node.expanded:
                    self.canvas.create_line(x + 7, y + 10, x + 7, y + 18, fill=self.palette["text"])
            icon_fill = self.palette["object"] if node.kind == "object" else self.palette["array"] if node.kind == "array" else self.palette["field"]
            self.canvas.create_rectangle(*icon_box, fill=icon_fill, outline=self.palette["border"])
            self._draw_icon_pair(icon_box, icon_pair, icon_gap, y + self.row_h // 2)
            text_x = icon_x + icon_w + 8
            self.canvas.create_text(text_x, y + self.row_h // 2, text=node.display_text, anchor="w", fill=self.palette["text"], font=self.tree_font)
            max_text_width = max(max_text_width, text_x + self.tree_font.measure(node.display_text) + 24)
        height = max(self.canvas.winfo_height(), len(self.visible) * self.row_h)
        self.canvas.configure(scrollregion=(0, 0, max_text_width, height))

    def _draw_vertical_connector(self, x: int, y1: int, y2: int, toggle_boxes) -> None:
        if y2 <= y1:
            return
        segments = [(y1, y2)]
        for box in toggle_boxes:
            bx1, by1, bx2, by2 = box
            if not (bx1 - 4 <= x <= bx2 + 4):
                continue
            next_segments = []
            cut1, cut2 = by1 - 1, by2 + 1
            for start, end in segments:
                if cut2 <= start or cut1 >= end:
                    next_segments.append((start, end))
                    continue
                if start < cut1:
                    next_segments.append((start, cut1))
                if cut2 < end:
                    next_segments.append((cut2, end))
            segments = next_segments
        for start, end in segments:
            if end - start >= 2:
                self.canvas.create_line(x, start, x, end, fill=self.palette["line"], dash=(2, 3))

    def _icon_pair_width(self, pair: tuple[str, str], gap: int) -> int:
        slot_w = max(self.tree_font.measure(pair[0]), self.tree_font.measure(pair[1]))
        return slot_w * 2 + gap

    def _draw_icon_pair(self, icon_box: tuple[int, int, int, int], pair: tuple[str, str], gap: int, y: int) -> None:
        left, right = pair
        slot_w = max(self.tree_font.measure(left), self.tree_font.measure(right))
        center_x = (icon_box[0] + icon_box[2]) / 2
        offset = (slot_w + gap) / 2
        self.canvas.create_text(center_x - offset, y, text=left, anchor="center", fill=self.palette["text"], font=self.tree_font)
        self.canvas.create_text(center_x + offset, y, text=right, anchor="center", fill=self.palette["text"], font=self.tree_font)

    def row_at(self, x: int, y: int) -> tuple[int | None, TreeNode | None]:
        cy = self.canvas.canvasy(y)
        idx = int(cy // self.row_h)
        if 0 <= idx < len(self.visible):
            return idx, self.visible[idx]
        return None, None

    def _click(self, event) -> None:
        idx, node = self.row_at(event.x, event.y)
        if node is None:
            self.selected = None
            self.draw()
            self.on_select(None)
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        box = self.toggle_boxes.get(idx)
        if box and box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
            node.expanded = not node.expanded
            refresh_to_root(node)
            self.draw()
            return
        self.selected = node
        self.draw()
        self.on_select(node)

    def _double_click(self, event) -> None:
        _idx, node = self.row_at(event.x, event.y)
        if node and node.has_children:
            node.expanded = not node.expanded
            refresh_to_root(node)
            self.selected = node
            self.draw()

    def _right_click(self, event) -> str:
        _idx, node = self.row_at(event.x, event.y)
        self.selected = node
        self.draw()
        self.on_context(event.x_root, event.y_root, node)
        return "break"

    def _wheel(self, event):
        units = -1 if event.delta > 0 else 1
        if event.state & 0x0001:
            self.canvas.xview_scroll(units * WHEEL_SCROLL_UNITS, "units")
        elif event.state & 0x0004:
            return self._font_wheel(event)
        else:
            self.canvas.yview_scroll(units * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _font_wheel(self, event):
        self.on_font_delta(1 if event.delta > 0 else -1)
        return "break"

    def expand_all(self, node: TreeNode | None = None) -> None:
        node = node or self.root_node
        if not node:
            return

        def walk(n: TreeNode) -> None:
            n.expanded = True
            for c in n.children:
                walk(c)

        walk(node)
        if self.root_node:
            refresh_tree_states(self.root_node)
        self.draw()

    def collapse_all(self) -> None:
        if not self.root_node:
            return

        def walk(node: TreeNode) -> None:
            node.expanded = node is self.root_node
            for child in node.children:
                walk(child)

        walk(self.root_node)
        refresh_tree_states(self.root_node)
        self.draw()

    def expand_item(self, node: TreeNode) -> None:
        def walk(n: TreeNode) -> None:
            n.expanded = True
            for c in n.children:
                walk(c)

        walk(node)
        refresh_to_root(node)
        self.draw()

    def collapse_item(self, node: TreeNode) -> None:
        node.expanded = False
        refresh_to_root(node)
        self.draw()

    def select_path(self, path: tuple[str, ...]) -> TreeNode | None:
        node = self.root_node
        if node is None:
            return None
        for part in path:
            found = next((child for child in node.children if child.label == part), None)
            if found is None:
                break
            node.expanded = True
            node = found
        self.selected = node
        refresh_tree_states(self.root_node)
        self.draw()
        if node in self.visible:
            idx = self.visible.index(node)
            total = max(1, len(self.visible) * self.row_h - self.canvas.winfo_height())
            self.canvas.yview_moveto(max(0, (idx * self.row_h - self.row_h) / total))
        return node
