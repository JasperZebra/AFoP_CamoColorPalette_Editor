"""
GearCamo Color Palette Editor  –  AFoP
=======================================
Double-click any color cell to pick a new color.
Only the RGB portion (after the alpha byte) is changed.
A .bak backup is created on Save.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os, shutil, colorsys

# ══════════════════════════════════════════════════════════════════════════════
#  FILE PARSING / SAVING
# ══════════════════════════════════════════════════════════════════════════════

def parse_rejuice(path):
    with open(path, "rb") as f:
        raw = f.read()
    tokens = [t for t in raw.decode("latin-1").split("\x00") if t.strip()]
    entries, i = [], 0
    while i < len(tokens):
        if tokens[i] == "GearCamoColorPalette" and i + 1 < len(tokens):
            entry = {"name": tokens[i+1],
                     "myPrimaryColor": None,
                     "mySecondaryColor": None,
                     "myTertiaryColor": None}
            j = i + 2
            CF = {"myPrimaryColor", "mySecondaryColor", "myTertiaryColor"}
            while j < len(tokens) and tokens[j] != "GearCamoColorPalette":
                if tokens[j] in CF and j + 1 < len(tokens):
                    entry[tokens[j]] = tokens[j+1]; j += 2
                else:
                    j += 1
            entries.append(entry); i = j
        else:
            i += 1
    return entries


def hex_str_to_rgb(val):
    if not val or not val.startswith("0x"):
        return None, None
    n = int(val, 16)
    return f"#{(n>>16)&0xFF:02x}{(n>>8)&0xFF:02x}{n&0xFF:02x}", (n>>24)&0xFF


def rgb_to_hex_str(html, alpha):
    r,g,b = int(html[1:3],16), int(html[3:5],16), int(html[5:7],16)
    return f"0x{(alpha<<24|r<<16|g<<8|b):08x}"


def save_rejuice(path, originals, edited):
    with open(path, "rb") as f: raw = f.read()
    data = bytearray(raw)

    for orig, edit in zip(originals, edited):
        name = orig["name"]
        # Locate this palette block by its exact name so we never touch other entries
        marker = ("GearCamoColorPalette\x00" + name + "\x00").encode("latin-1")
        block_start = data.find(marker)
        if block_start == -1:
            continue
        # Block ends at start of the next palette entry (or EOF)
        block_end = data.find(b"GearCamoColorPalette\x00", block_start + len(marker))
        if block_end == -1:
            block_end = len(data)

        for field in ("myPrimaryColor", "mySecondaryColor", "myTertiaryColor"):
            ov, nv = orig[field], edit[field]
            if not ov or not nv or ov == nv:
                continue
            old_bytes = (field + "\x00" + ov).encode("latin-1")
            new_bytes = (field + "\x00" + nv).encode("latin-1")
            pos = data.find(old_bytes, block_start, block_end)
            if pos == -1:
                continue
            data[pos:pos + len(old_bytes)] = new_bytes

    with open(path, "wb") as f: f.write(bytes(data))

def luma(html):
    return 0.299*int(html[1:3],16) + 0.587*int(html[3:5],16) + 0.114*int(html[5:7],16)


# ══════════════════════════════════════════════════════════════════════════════
#  THEME
# ══════════════════════════════════════════════════════════════════════════════

BG      = "#1e1e2e"
SURFACE = "#2a2a3e"
OVERLAY = "#313244"
TEXT    = "#cdd6f4"
SUBTEXT = "#6c7086"
MAUVE   = "#cba6f7"
GREEN   = "#a6e3a1"
BLUE    = "#89dceb"
RED     = "#f38ba8"

ROW_H      = 37.4
COL_WIDTHS = [280, 210, 210, 210]
FIELDS     = ("myPrimaryColor","mySecondaryColor","myTertiaryColor")
HEADERS    = ("CamoColorPalette","myPrimaryColor","mySecondaryColor","myTertiaryColor")


# ══════════════════════════════════════════════════════════════════════════════
#  MODERN COLOR PICKER  (self-contained Toplevel)
# ══════════════════════════════════════════════════════════════════════════════

class ColorPicker(tk.Toplevel):
    """
    A modern HSV color picker with:
      • Saturation/Value square (click + drag)
      • Hue bar  (click + drag)
      • Live hex input
      • R G B sliders
      • Before / After preview strip
    Returns result via .result  (#rrggbb or None if cancelled)
    """

    PAD  = 16

    def __init__(self, parent, initial_color="#808080", title="Pick a colour",
                 sq_width=450, sq_height=220, bar_height=22, preview_height=52):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.result = None

        self.SQ_W      = sq_width       # width of the SV gradient area
        self.SQ_H      = sq_height      # height of the SV gradient area
        self.BAR       = bar_height     # height of the hue rainbow bar
        self.PREVIEW_H = preview_height # height of the before/after preview strip

        # parse initial
        r,g,b = int(initial_color[1:3],16), int(initial_color[3:5],16), int(initial_color[5:7],16)
        h,s,v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        self._h = h   # 0-1
        self._s = s   # 0-1
        self._v = v   # 0-1
        self._initial = initial_color
        self._dragging = None   # 'sq' | 'hue'

        self._build()
        self._redraw_sq()
        self._redraw_hue()
        self._update_all()

        # center over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width()//2  - self.winfo_width()//2
        py = parent.winfo_rooty() + parent.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self):
        P = self.PAD

        outer = tk.Frame(self, bg=BG, padx=P, pady=P)
        outer.pack(fill="both", expand=True)

        # ── SV gradient canvas ──
        self.sq_canvas = tk.Canvas(outer, width=self.SQ_W, height=self.SQ_H,
                                    highlightthickness=1, highlightbackground=OVERLAY,
                                    cursor="crosshair")
        self.sq_canvas.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.sq_canvas.bind("<ButtonPress-1>",   self._sq_press)
        self.sq_canvas.bind("<B1-Motion>",        self._sq_drag)
        self.sq_canvas.bind("<ButtonRelease-1>",  lambda e: self._stop_drag())
        self.sq_canvas.bind("<Configure>",        lambda e: self._redraw_sq())

        # ── hue bar ──
        self.hue_canvas = tk.Canvas(outer, width=self.SQ_W, height=self.BAR,
                                     highlightthickness=1, highlightbackground=OVERLAY,
                                     cursor="sb_h_double_arrow")
        self.hue_canvas.grid(row=1, column=0, columnspan=2, pady=(8,0), sticky="ew")
        self.hue_canvas.bind("<ButtonPress-1>",  self._hue_press)
        self.hue_canvas.bind("<B1-Motion>",       self._hue_drag)
        self.hue_canvas.bind("<ButtonRelease-1>", lambda e: self._stop_drag())
        self.hue_canvas.bind("<Configure>",       lambda e: self._redraw_hue())

        # ── before / after preview ──
        prev_frame = tk.Frame(outer, bg=BG)
        prev_frame.grid(row=2, column=0, columnspan=2, pady=(10,0), sticky="ew")

        tk.Label(prev_frame, text="Before", bg=BG, fg=SUBTEXT,
                 font=("Consolas",8)).pack(side="left")
        tk.Label(prev_frame, text="After", bg=BG, fg=SUBTEXT,
                 font=("Consolas",8)).pack(side="right")

        pv = tk.Frame(outer, height=self.PREVIEW_H, bg=BG)
        pv.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2,0))
        pv.grid_propagate(False)

        self.prev_before = tk.Frame(pv, bg=self._initial)
        self.prev_before.place(relx=0, rely=0, relwidth=0.5, relheight=1)
        self.prev_after  = tk.Frame(pv, bg=self._initial)
        self.prev_after .place(relx=0.5, rely=0, relwidth=0.5, relheight=1)

        # ── hex input ──
        hex_row = tk.Frame(outer, bg=BG)
        hex_row.grid(row=4, column=0, columnspan=2, pady=(12,0), sticky="w")

        tk.Label(hex_row, text="#", bg=BG, fg=SUBTEXT,
                 font=("Consolas",12,"bold")).pack(side="left")
        self._hex_var = tk.StringVar()
        self._hex_entry = tk.Entry(hex_row, textvariable=self._hex_var,
                                    width=7, bg=OVERLAY, fg=TEXT,
                                    insertbackground=TEXT, relief="flat",
                                    font=("Consolas",12,"bold"))
        self._hex_entry.pack(side="left", ipady=4, padx=(2,8))
        self._hex_var.trace_add("write", self._on_hex_typed)

        # eyedropper label (cosmetic)
        tk.Label(hex_row, text="HEX", bg=BG, fg=SUBTEXT,
                 font=("Consolas",8)).pack(side="left")

        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        # ── RGB sliders ──
        sliders = tk.Frame(outer, bg=BG)
        sliders.grid(row=5, column=0, columnspan=2, pady=(10,0), sticky="ew")

        self._r_var = tk.IntVar()
        self._g_var = tk.IntVar()
        self._b_var = tk.IntVar()

        for label, var, color in (("R", self._r_var, RED),
                                   ("G", self._g_var, GREEN),
                                   ("B", self._b_var, BLUE)):
            row = tk.Frame(sliders, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=BG, fg=color,
                     font=("Consolas",10,"bold"), width=2).pack(side="left")
            sl = tk.Scale(row, variable=var, from_=0, to=255,
                          orient="horizontal", bg=BG, fg=TEXT,
                          troughcolor=OVERLAY, highlightthickness=0,
                          activebackground=color, sliderrelief="flat",
                          length=self.SQ_W-30, showvalue=True, resolution=1,
                          command=lambda val, v=var: self._on_slider(v))
            sl.pack(side="left", fill="x", expand=True)

        # ── buttons ──
        btn_row = tk.Frame(outer, bg=BG)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(14,0), sticky="ew")

        def mkbtn(text, cmd, fg):
            tk.Button(btn_row, text=text, command=cmd,
                      bg=OVERLAY, fg=fg, relief="flat",
                      font=("Consolas",10,"bold"), padx=16, pady=6,
                      cursor="hand2", activebackground="#45475a",
                      activeforeground=fg).pack(side="left", expand=True, fill="x", padx=(0,4))

        mkbtn("✓  Apply", self._apply, GREEN)
        mkbtn("✗  Cancel", self._cancel, RED)

        self.bind("<Return>",  lambda e: self._apply())
        self.bind("<Escape>",  lambda e: self._cancel())

    # ── drawing ───────────────────────────────────────────────────────────────

    def _redraw_sq(self):
        """Draw SV gradient for current hue using a PhotoImage."""
        c = self.sq_canvas
        c.delete("all")
        W = c.winfo_width()  or self.SQ_W
        H = c.winfo_height() or self.SQ_H
        if W < 2 or H < 2:
            return
        img = tk.PhotoImage(width=W, height=H)
        rows = []
        for row in range(H):
            v = 1.0 - row / (H - 1)
            cols = []
            for col in range(W):
                s = col / (W - 1)
                r, g, b = colorsys.hsv_to_rgb(self._h, s, v)
                cols.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
            rows.append("{" + " ".join(cols) + "}")
        img.put(" ".join(rows))
        c._img = img
        c.create_image(0, 0, anchor="nw", image=img)
        # crosshair
        cx = int(self._s * (W-1))
        cy = int((1 - self._v) * (H-1))
        r = 7
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="white", width=2)
        c.create_oval(cx-r+1, cy-r+1, cx+r-1, cy+r-1, outline="black", width=1)

    def _redraw_hue(self):
        """Draw rainbow hue bar."""
        c = self.hue_canvas
        c.delete("all")
        W = c.winfo_width()  or self.SQ_W
        H = c.winfo_height() or self.BAR
        if W < 2 or H < 2:
            return
        img = tk.PhotoImage(width=W, height=H)
        row_data = []
        for col in range(W):
            hh = col / (W - 1)
            r, g, b = colorsys.hsv_to_rgb(hh, 1, 1)
            row_data.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
        row_str = "{" + " ".join(row_data) + "}"
        img.put(" ".join([row_str]*H))
        c._img = img
        c.create_image(0, 0, anchor="nw", image=img)
        # marker
        mx = int(self._h * (W-1))
        c.create_rectangle(mx-3, 0, mx+3, H, outline="white", width=2)

    # ── update helpers ────────────────────────────────────────────────────────

    def _hsv_to_html(self):
        r,g,b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def _update_all(self, source=None):
        html = self._hsv_to_html()
        # preview
        self.prev_after.configure(bg=html)
        # hex entry (suppress re-trigger)
        if source != "hex":
            self._hex_var.trace_remove("write", self._hex_var.trace_info()[0][1]) \
                if self._hex_var.trace_info() else None
            self._hex_var.set(html[1:].upper())
            self._hex_var.trace_add("write", self._on_hex_typed)
        # sliders
        r,g,b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        if source != "slider":
            self._r_var.set(int(r*255))
            self._g_var.set(int(g*255))
            self._b_var.set(int(b*255))

    # ── events ────────────────────────────────────────────────────────────────

    def _sq_press(self, e):
        self._dragging = "sq"; self._sq_move(e.x, e.y)

    def _sq_drag(self, e):
        if self._dragging == "sq": self._sq_move(e.x, e.y)

    def _sq_move(self, x, y):
        W = self.sq_canvas.winfo_width()  or self.SQ_W
        H = self.sq_canvas.winfo_height() or self.SQ_H
        self._s = max(0, min(1, x / (W-1)))
        self._v = max(0, min(1, 1 - y / (H-1)))
        self._redraw_sq()
        self._update_all()

    def _hue_press(self, e):
        self._dragging = "hue"; self._hue_move(e.x)

    def _hue_drag(self, e):
        if self._dragging == "hue": self._hue_move(e.x)

    def _hue_move(self, x):
        W = self.hue_canvas.winfo_width() or self.SQ_W
        self._h = max(0, min(1, x / (W-1)))
        self._redraw_sq()
        self._redraw_hue()
        self._update_all()

    def _stop_drag(self):
        self._dragging = None

    def _on_hex_typed(self, *_):
        raw = self._hex_var.get().strip().lstrip("#")
        if len(raw) == 6:
            try:
                r,g,b = int(raw[0:2],16), int(raw[2:4],16), int(raw[4:6],16)
                self._h, self._s, self._v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                self._redraw_sq()
                self._redraw_hue()
                self._update_all(source="hex")
            except ValueError:
                pass

    def _on_slider(self, changed_var):
        r,g,b = self._r_var.get(), self._g_var.get(), self._b_var.get()
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        self._redraw_sq()
        self._redraw_hue()
        self._update_all(source="slider")

    def _apply(self):
        self.result = self._hsv_to_html()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def ask_color(parent, initial="#808080", title="Pick a colour"):
    """Blocking call – returns '#rrggbb' or None."""
    picker = ColorPicker(parent, initial, title)
    parent.wait_window(picker)
    return picker.result


# ══════════════════════════════════════════════════════════════════════════════
#  CANVAS TABLE
# ══════════════════════════════════════════════════════════════════════════════

class ColorTable(tk.Frame):
    def __init__(self, master, on_edit_callback, **kw):
        super().__init__(master, bg=BG, **kw)
        self.on_edit  = on_edit_callback
        self.entries  = []
        self.visible  = []
        self._build()

    def _build(self):
        self.header_canvas = tk.Canvas(self, height=ROW_H, bg=OVERLAY,
                                        highlightthickness=0)
        self.header_canvas.pack(fill="x")
        self.header_canvas.bind("<Configure>", lambda e: self._draw_header())

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, bg=SURFACE, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Configure>",       lambda e: self._redraw())
        self.canvas.bind("<Double-Button-1>",  self._on_dbl)
        self.canvas.bind("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1,"units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll( 1,"units"))

    def load(self, entries, visible=None):
        self.entries = entries
        self.visible = visible if visible is not None else list(range(len(entries)))
        self._redraw()

    def _draw_header(self):
        c = self.header_canvas; c.delete("all"); x = 0
        for h, w in zip(HEADERS, COL_WIDTHS):
            c.create_rectangle(x, 0, x+w, ROW_H, fill=OVERLAY, outline="#45475a")
            c.create_text(x+w//2, ROW_H//2, text=h, fill=MAUVE,
                          font=("Consolas",10,"bold"), anchor="center")
            x += w

    def _redraw(self):
        c = self.canvas; c.delete("all")
        total_h = ROW_H * len(self.visible)
        total_w = sum(COL_WIDTHS)
        c.configure(scrollregion=(0,0,total_w,max(total_h,1)))

        for row_i, entry_idx in enumerate(self.visible):
            e   = self.entries[entry_idx]
            y0  = row_i * ROW_H; y1 = y0 + ROW_H
            row_bg = SURFACE if row_i%2==0 else "#252538"

            x = 0
            c.create_rectangle(x, y0, x+COL_WIDTHS[0], y1, fill=row_bg, outline="#3a3a52")
            c.create_text(x+10, (y0+y1)//2, text=e["name"], fill=TEXT,
                          font=("Consolas",10), anchor="w")
            x += COL_WIDTHS[0]

            for fi, field in enumerate(FIELDS):
                w   = COL_WIDTHS[fi+1]
                val = e[field]
                html, _ = hex_str_to_rgb(val) if val else (None, None)
                c.create_rectangle(x, y0, x+w, y1, fill=row_bg, outline="#3a3a52")
                if html:
                    pad = 6
                    c.create_rectangle(x+pad, y0+4, x+w-pad, y1-4,
                                       fill=html, outline="#000000")
                    fg = "#000000" if luma(html)>128 else "#ffffff"
                    c.create_text(x+w//2, (y0+y1)//2, text=val, fill=fg,
                                  font=("Consolas",9), anchor="center")
                else:
                    c.create_text(x+w//2, (y0+y1)//2, text="—",
                                  fill=SUBTEXT, font=("Consolas",10), anchor="center")
                x += w

        self._draw_header()

    def _on_dbl(self, event):
        cy = self.canvas.canvasy(event.y); cx = event.x
        row_i = int(cy // ROW_H)
        if row_i < 0 or row_i >= len(self.visible): return
        x, col = 0, -1
        for ci, w in enumerate(COL_WIDTHS):
            if cx < x+w: col = ci; break
            x += w
        if col <= 0: return
        field     = FIELDS[col-1]
        entry_idx = self.visible[row_i]
        e         = self.entries[entry_idx]
        val       = e[field]
        init_color, alpha = hex_str_to_rgb(val) if val else ("#808080", 0x80)
        if alpha is None: alpha = 0x80

        new_html = ask_color(self.winfo_toplevel(),
                             initial=init_color,
                             title=f"{field}  ·  {e['name']}")
        if new_html is None: return
        e[field] = rgb_to_hex_str(new_html, alpha)
        self.on_edit(entry_idx)
        self._redraw()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AFoP CamoColorPalette Editor | Made By: Jasper_Zebra | Version 1.0")
        self.configure(bg=BG)
        self.geometry("960x700")
        self.minsize(700,400)

        self.filepath         = None
        self.entries_original = []
        self.entries_edited   = []

        self._build_ui()
        self._try_autoload()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=OVERLAY,
                        troughcolor=SURFACE, arrowcolor=TEXT)

        tb = tk.Frame(self, bg=BG); tb.pack(fill="x", padx=10, pady=8)

        def mkbtn(parent, text, cmd, fg=MAUVE, side="left"):
            b = tk.Button(parent, text=text, command=cmd,
                          bg=OVERLAY, fg=fg, activebackground="#45475a",
                          activeforeground=fg, relief="flat",
                          font=("Consolas",10,"bold"), padx=12, pady=4,
                          cursor="hand2", bd=0)
            b.pack(side=side, padx=(0,6)); return b

        mkbtn(tb, "📂  Open", self._open_file)
        self.lbl_file = tk.Label(tb, text="No file loaded", bg=BG,
                                  fg=SUBTEXT, font=("Consolas",9))
        self.lbl_file.pack(side="left", padx=6)
        self.btn_save = mkbtn(tb, "💾  Save", self._save, GREEN, "right")
        self.btn_save["state"] = "disabled"

        sf = tk.Frame(self, bg=BG); sf.pack(fill="x", padx=10, pady=(0,4))
        tk.Label(sf, text="🔍", bg=BG, fg=TEXT, font=("Consolas",11)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter())
        tk.Entry(sf, textvariable=self.search_var, bg=OVERLAY, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Consolas",10), width=35).pack(side="left", padx=6, ipady=3)
        self.lbl_count = tk.Label(sf, text="", bg=BG, fg=SUBTEXT,
                                   font=("Consolas",9))
        self.lbl_count.pack(side="left", padx=4)

        self.table = ColorTable(self, on_edit_callback=lambda _: None)
        self.table.pack(fill="both", expand=True, padx=10, pady=(0,4))

        tk.Label(self, text="Double-click a color cell to edit  ·  Alpha byte preserved automatically",
                 bg=BG, fg=SUBTEXT, font=("Consolas",8)).pack(pady=(0,6))

    def _try_autoload(self):
        default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "gearcamo_colorpalettes.rejuice")
        if os.path.exists(default): self._load(default)

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open .rejuice file",
            filetypes=[("Rejuice files","*.rejuice"),("All files","*.*")])
        if path: self._load(path)

    def _load(self, path):
        try:
            entries = parse_rejuice(path)
        except Exception as e:
            messagebox.showerror("Parse error", str(e)); return
        self.filepath         = path
        self.entries_original = entries
        self.entries_edited   = [dict(e) for e in entries]
        self.lbl_file.config(text=os.path.basename(path), fg=TEXT)
        self.btn_save["state"] = "normal"
        self.table.load(self.entries_edited)
        self._update_count(len(entries))

    def _update_count(self, shown=None):
        total = len(self.entries_edited)
        shown = total if shown is None else shown
        self.lbl_count.config(
            text=f"{shown} / {total} entries" if shown!=total else f"{total} entries")

    def _filter(self):
        ft = self.search_var.get().lower()
        vis = ([i for i,e in enumerate(self.entries_edited) if ft in e["name"].lower()]
               if ft else list(range(len(self.entries_edited))))
        self.table.load(self.entries_edited, vis)
        self._update_count(len(vis))

    def _save(self):
        if not self.filepath: return
        try:
            shutil.copy2(self.filepath, self.filepath+".bak")
            save_rejuice(self.filepath, self.entries_original, self.entries_edited)
            self.entries_original = [dict(e) for e in self.entries_edited]
            messagebox.showinfo("Saved ✓",
                f"Saved.\nBackup: {os.path.basename(self.filepath)}.bak")
        except Exception as e:
            messagebox.showerror("Save error", str(e))


if __name__ == "__main__":
    App().mainloop()