import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import os

# ======================================================================
# Diálogo para editar texto, fonte e tamanho
# ======================================================================
class TextEditDialog(tk.Toplevel):
    def __init__(self, parent, title="", initial_text="", fontsize=12, fontname="helv"):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.transient(parent)
        self.grab_set()

        frm = ttk.Frame(self, padding=10)
        frm.pack()

        ttk.Label(frm, text="Texto:").grid(row=0, column=0, sticky='w', pady=(0,2))
        self.text_widget = tk.Text(frm, height=5, width=40)
        self.text_widget.insert('1.0', initial_text)
        self.text_widget.grid(row=0, column=1, pady=(0,2))

        ttk.Label(frm, text="Fonte:").grid(row=1, column=0, sticky='w', pady=2)
        self.font_var = tk.StringVar(value=fontname)
        font_combo = ttk.Combobox(frm, textvariable=self.font_var,
                                  values=['helv', 'times', 'cour', 'symb', 'ding'],
                                  state='readonly', width=15)
        font_combo.grid(row=1, column=1, pady=2, sticky='w')

        ttk.Label(frm, text="Tamanho:").grid(row=2, column=0, sticky='w', pady=2)
        self.size_var = tk.IntVar(value=fontsize)
        size_spin = ttk.Spinbox(frm, from_=6, to=100, textvariable=self.size_var, width=5)
        size_spin.grid(row=2, column=1, pady=2, sticky='w')

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=3, columnspan=2, pady=(10,0))
        ttk.Button(btn_frame, text="OK", command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.wait_window()

    def on_ok(self):
        text = self.text_widget.get('1.0', 'end-1c')
        self.result = (text, self.font_var.get(), self.size_var.get())
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


# ======================================================================
# Objeto caixa de texto no canvas (editor)
# ======================================================================
class TextBox:
    def __init__(self, canvas, x1, y1, x2, y2, text="", fontname="helv", fontsize=12):
        self.canvas = canvas
        self.rect = [x1, y1, x2, y2]           # coordenadas no canvas
        self.text = text
        self.fontname = fontname
        self.fontsize = fontsize
        self.items = []                         # ids dos objetos no canvas
        self.handles = {}                       # ids das alças
        self.draw()

    def draw(self):
        # Remove itens antigos
        for iid in self.items:
            self.canvas.delete(iid)
        self.items.clear()
        self.handles.clear()

        # Retângulo principal
        r = self.canvas.create_rectangle(
            self.rect[0], self.rect[1], self.rect[2], self.rect[3],
            outline='#0078D7', fill='', width=2, stipple='gray25'
        )
        self.items.append(r)

        # Texto centralizado
        txt_id = self.canvas.create_text(
            (self.rect[0] + self.rect[2]) / 2,
            (self.rect[1] + self.rect[3]) / 2,
            text=self.text,
            font=('Helvetica', self.fontsize),
            anchor='center',
            width=self.rect[2] - self.rect[0] - 6
        )
        self.items.append(txt_id)

        # Alças (pequenos quadrados)
        hw = 4  # metade do tamanho
        positions = {
            'nw': (self.rect[0], self.rect[1]),
            'n':  ((self.rect[0] + self.rect[2]) / 2, self.rect[1]),
            'ne': (self.rect[2], self.rect[1]),
            'w':  (self.rect[0], (self.rect[1] + self.rect[3]) / 2),
            'e':  (self.rect[2], (self.rect[1] + self.rect[3]) / 2),
            'sw': (self.rect[0], self.rect[3]),
            's':  ((self.rect[0] + self.rect[2]) / 2, self.rect[3]),
            'se': (self.rect[2], self.rect[3]),
        }
        for key, (cx, cy) in positions.items():
            hid = self.canvas.create_rectangle(
                cx - hw, cy - hw, cx + hw, cy + hw,
                fill='white', outline='black'
            )
            self.handles[key] = hid
            self.items.append(hid)

        # Agrupar tags
        for iid in self.items:
            self.canvas.itemconfig(iid, tags=('textbox',))

    def update_text(self, text, fontname, fontsize):
        self.text = text
        self.fontname = fontname
        self.fontsize = fontsize
        self.draw()

    def contains(self, x, y):
        return self.rect[0] <= x <= self.rect[2] and self.rect[1] <= y <= self.rect[3]

    def get_handle(self, x, y, threshold=5):
        for key, hid in self.handles.items():
            coords = self.canvas.coords(hid)
            if len(coords) == 4 and coords[0] - threshold <= x <= coords[2] + threshold and \
               coords[1] - threshold <= y <= coords[3] + threshold:
                return key
        return None

    def move(self, dx, dy):
        self.rect[0] += dx
        self.rect[1] += dy
        self.rect[2] += dx
        self.rect[3] += dy
        for iid in self.items:
            self.canvas.move(iid, dx, dy)


# ======================================================================
# Editor de uma página do PDF (nova janela)
# ======================================================================
class PDFPageEditor(tk.Toplevel):
    def __init__(self, master, pdf_path, page_num, on_save_callback=None):
        super().__init__(master)
        self.title(f"Editando página {page_num+1} – {os.path.basename(pdf_path)}")
        self.geometry("800x700")
        self.pdf_path = pdf_path
        self.page_num = page_num
        self.on_save_callback = on_save_callback

        # Abrir documento e página
        self.doc = fitz.open(pdf_path)
        self.page = self.doc.load_page(page_num)
        self.scale = 150 / 72.0            # DPI da visualização

        # Imagem da página
        mat = fitz.Matrix(self.scale, self.scale)
        pix = self.page.get_pixmap(matrix=mat)
        self.img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.photo = ImageTk.PhotoImage(self.img)

        # Barra de ferramentas
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Adicionar Caixa de Texto", command=self.start_draw).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(toolbar, text="Salvar no original", command=lambda: self.save(overwrite=True)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="Salvar como...", command=lambda: self.save(overwrite=False)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        # Canvas com scrollbars
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg='#E0E0E0', cursor="cross")
        hbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.config(scrollregion=(0, 0, self.img.width, self.img.height))

        # Estado interno
        self.textboxes = []            # lista de TextBox
        self.mode = 'idle'            # 'idle' | 'drawing' | 'dragging' | 'resizing'
        self.drawing_start = None
        self.draw_rect_id = None
        self.drag_data = None
        self.resize_data = None

        # Eventos do mouse
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-1>", self.on_double_click)

    def start_draw(self):
        self.mode = 'drawing'
        self.canvas.config(cursor="crosshair")

    def on_press(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        if self.mode == 'drawing':
            self.drawing_start = (x, y)
            self.draw_rect_id = self.canvas.create_rectangle(
                x, y, x, y, outline='red', dash=(3, 3)
            )
        elif self.mode == 'idle':
            # Verifica se clicou numa alça
            for box in self.textboxes:
                handle = box.get_handle(x, y)
                if handle:
                    self.mode = 'resizing'
                    self.resize_data = {
                        'box': box,
                        'handle': handle,
                        'start_x': x,
                        'start_y': y,
                        'orig_rect': box.rect.copy()
                    }
                    return
            # Verifica se clicou dentro de uma caixa
            for box in self.textboxes:
                if box.contains(x, y):
                    self.mode = 'dragging'
                    self.drag_data = {
                        'box': box,
                        'start_x': x,
                        'start_y': y,
                        'orig_x': box.rect[0],
                        'orig_y': box.rect[1]
                    }
                    self.canvas.config(cursor="fleur")
                    return

    def on_motion(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        if self.mode == 'drawing' and self.draw_rect_id:
            x1, y1 = self.drawing_start
            self.canvas.coords(self.draw_rect_id, x1, y1, x, y)

        elif self.mode == 'dragging' and self.drag_data:
            box = self.drag_data['box']
            new_x = self.drag_data['orig_x'] + (x - self.drag_data['start_x'])
            new_y = self.drag_data['orig_y'] + (y - self.drag_data['start_y'])
            dx = new_x - box.rect[0]
            dy = new_y - box.rect[1]
            box.move(dx, dy)

        elif self.mode == 'resizing' and self.resize_data:
            box = self.resize_data['box']
            handle = self.resize_data['handle']
            orig = self.resize_data['orig_rect']

            new_rect = orig.copy()
            if handle == 'nw':
                new_rect[0] = min(x, orig[2] - 20)
                new_rect[1] = min(y, orig[3] - 20)
            elif handle == 'ne':
                new_rect[2] = max(x, orig[0] + 20)
                new_rect[1] = min(y, orig[3] - 20)
            elif handle == 'sw':
                new_rect[0] = min(x, orig[2] - 20)
                new_rect[3] = max(y, orig[1] + 20)
            elif handle == 'se':
                new_rect[2] = max(x, orig[0] + 20)
                new_rect[3] = max(y, orig[1] + 20)
            elif handle == 'n':
                new_rect[1] = min(y, orig[3] - 20)
            elif handle == 's':
                new_rect[3] = max(y, orig[1] + 20)
            elif handle == 'w':
                new_rect[0] = min(x, orig[2] - 20)
            elif handle == 'e':
                new_rect[2] = max(x, orig[0] + 20)

            # Tamanho mínimo
            if new_rect[2] - new_rect[0] < 20:
                if handle in ('w', 'nw', 'sw'):
                    new_rect[0] = new_rect[2] - 20
                else:
                    new_rect[2] = new_rect[0] + 20
            if new_rect[3] - new_rect[1] < 20:
                if handle in ('n', 'nw', 'ne'):
                    new_rect[1] = new_rect[3] - 20
                else:
                    new_rect[3] = new_rect[1] + 20

            box.rect = new_rect
            box.draw()

    def on_release(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        if self.mode == 'drawing':
            self.mode = 'idle'
            self.canvas.config(cursor="")
            if self.draw_rect_id:
                self.canvas.delete(self.draw_rect_id)
                self.draw_rect_id = None
            if self.drawing_start:
                x1, y1 = self.drawing_start
                x2, y2 = x, y
                if x1 > x2: x1, x2 = x2, x1
                if y1 > y2: y1, y2 = y2, y1
                if x2 - x1 > 10 and y2 - y1 > 10:
                    self.add_text_box(x1, y1, x2, y2)
            self.drawing_start = None

        elif self.mode in ('dragging', 'resizing'):
            self.mode = 'idle'
            self.canvas.config(cursor="")
            self.drag_data = None
            self.resize_data = None

    def add_text_box(self, x1, y1, x2, y2):
        dialog = TextEditDialog(self, title="Nova caixa de texto",
                                initial_text="", fontsize=12, fontname="helv")
        if dialog.result:
            text, fontname, fontsize = dialog.result
            box = TextBox(self.canvas, x1, y1, x2, y2,
                          text=text, fontname=fontname, fontsize=fontsize)
            self.textboxes.append(box)

    def on_double_click(self, event):
        if self.mode != 'idle':
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for box in self.textboxes:
            if box.contains(x, y):
                dialog = TextEditDialog(self, title="Editar texto",
                                        initial_text=box.text,
                                        fontsize=box.fontsize,
                                        fontname=box.fontname)
                if dialog.result:
                    text, fontname, fontsize = dialog.result
                    box.update_text(text, fontname, fontsize)
                return

    def save(self, overwrite=True):
        # Aplica as caixas de texto na página real do PDF
        for box in self.textboxes:
            x0 = box.rect[0] / self.scale
            y0 = box.rect[1] / self.scale
            x1 = box.rect[2] / self.scale
            y1 = box.rect[3] / self.scale
            rect = fitz.Rect(x0, y0, x1, y1)

            font_map = {
                'helv': 'Helvetica',
                'times': 'Times-Roman',
                'cour': 'Courier',
                'symb': 'Symbol',
                'ding': 'ZapfDingbats'
            }
            pdf_font = font_map.get(box.fontname, 'Helvetica')

            self.page.insert_textbox(rect, box.text,
                                     fontname=pdf_font,
                                     fontsize=box.fontsize,
                                     align=0)

        try:
            if overwrite:
                # Preserva criptografia existente
                self.doc.save(self.pdf_path, incremental=True,
                              encryption=fitz.PDF_ENCRYPT_KEEP)
                msg = "PDF original atualizado com sucesso."
            else:
                new_path = filedialog.asksaveasfilename(
                    defaultextension=".pdf",
                    filetypes=[("PDF", "*.pdf")],
                    title="Salvar PDF modificado como"
                )
                if not new_path:
                    return
                self.doc.save(new_path)
                msg = f"PDF salvo em:\n{new_path}"

            self.doc.close()
            messagebox.showinfo("Sucesso", msg)
            if self.on_save_callback:
                self.on_save_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")

    def destroy(self):
        if hasattr(self, 'doc'):
            try:
                self.doc.close()
            except:
                pass
        super().destroy()


# ======================================================================
# Aplicação principal (seleção múltipla com Shift/Ctrl e borda vermelha)
# ======================================================================
class PDFManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Gerenciador de PDFs – Unir, Dividir e Editar")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        self.pdf_files = []
        self.thumb_widgets = []          # (frame, path, page_num)
        self.thumbnail_size = (180, 250)

        # Controle de seleção múltipla
        self.selected_pages = set()      # conjunto de (path, page_num)
        self.last_clicked_index = None   # índice em thumb_widgets (âncora para Shift)

        self.setup_ui()

    def setup_ui(self):
        main_panel = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_panel.pack(fill=tk.BOTH, expand=True)

        # Painel central (miniaturas)
        center_frame = ttk.Frame(main_panel)
        main_panel.add(center_frame, weight=3)

        self.canvas = tk.Canvas(center_frame, bg='#f0f0f0')
        v_scroll = ttk.Scrollbar(center_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(center_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.canvas.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')

        center_frame.rowconfigure(0, weight=1)
        center_frame.columnconfigure(0, weight=1)

        self.thumb_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.thumb_frame, anchor='nw')
        self.thumb_frame.bind("<Configure>", self.on_frame_configure)

        # Painel direito (lista e controles)
        right_frame = ttk.Frame(main_panel, width=250)
        main_panel.add(right_frame, weight=1)

        ttk.Label(right_frame, text="PDFs carregados:").pack(anchor='w', pady=(5, 0))
        self.pdf_listbox = tk.Listbox(right_frame, selectmode=tk.EXTENDED, height=10)
        self.pdf_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Adicionar PDF", command=self.add_pdf).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Remover PDF", command=self.remove_pdf).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Mover ↑", command=self.move_up).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Mover ↓", command=self.move_down).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Limpar Tudo", command=self.clear_all).pack(fill=tk.X, pady=1)

        ttk.Separator(right_frame).pack(fill=tk.X, pady=10)

        ttk.Button(right_frame, text="Unir Páginas Selecionadas", command=self.merge_selected).pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="Unir Todos os PDFs", command=self.merge_all_pdfs).pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="Extrair Páginas Selecionadas", command=self.extract_selected).pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="Dividir PDF em Páginas", command=self.split_pdfs).pack(fill=tk.X, pady=2)

        ttk.Separator(right_frame).pack(fill=tk.X, pady=10)
        ttk.Button(right_frame, text="Selecionar Todas", command=self.select_all).pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="Desselecionar Todas", command=self.deselect_all).pack(fill=tk.X, pady=2)

        self.status = ttk.Label(self.root, text="Pronto", relief=tk.SUNKEN, anchor='w')
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def update_status(self, msg):
        self.status.config(text=msg)
        self.root.update_idletasks()

    # ----- Gerenciamento da lista de PDFs -----
    def add_pdf(self):
        files = filedialog.askopenfilenames(
            title="Selecionar PDF(s)",
            filetypes=[("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")]
        )
        if files:
            for f in files:
                if f not in self.pdf_files:
                    self.pdf_files.append(f)
                    self.pdf_listbox.insert(tk.END, os.path.basename(f))
            self.refresh_thumbnails()

    def remove_pdf(self):
        selected = self.pdf_listbox.curselection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um PDF na lista para remover.")
            return
        for idx in sorted(selected, reverse=True):
            del self.pdf_files[idx]
            self.pdf_listbox.delete(idx)
        self.refresh_thumbnails()

    def move_up(self):
        selected = self.pdf_listbox.curselection()
        if not selected or len(selected) > 1:
            messagebox.showinfo("Aviso", "Selecione exatamente um PDF para mover.")
            return
        idx = selected[0]
        if idx == 0:
            return
        self.pdf_files[idx], self.pdf_files[idx - 1] = self.pdf_files[idx - 1], self.pdf_files[idx]
        text = self.pdf_listbox.get(idx)
        self.pdf_listbox.delete(idx)
        self.pdf_listbox.insert(idx - 1, text)
        self.pdf_listbox.selection_set(idx - 1)
        self.refresh_thumbnails()

    def move_down(self):
        selected = self.pdf_listbox.curselection()
        if not selected or len(selected) > 1:
            messagebox.showinfo("Aviso", "Selecione exatamente um PDF para mover.")
            return
        idx = selected[0]
        if idx == len(self.pdf_files) - 1:
            return
        self.pdf_files[idx], self.pdf_files[idx + 1] = self.pdf_files[idx + 1], self.pdf_files[idx]
        text = self.pdf_listbox.get(idx)
        self.pdf_listbox.delete(idx)
        self.pdf_listbox.insert(idx + 1, text)
        self.pdf_listbox.selection_set(idx + 1)
        self.refresh_thumbnails()

    def clear_all(self):
        self.pdf_files.clear()
        self.pdf_listbox.delete(0, tk.END)
        self.refresh_thumbnails()

    # ----- Miniaturas e seleção -----
    def refresh_thumbnails(self):
        self.update_status("Gerando miniaturas...")
        self.root.config(cursor="watch")
        for widget in self.thumb_frame.winfo_children():
            widget.destroy()
        self.thumb_widgets.clear()
        self.selected_pages.clear()
        self.last_clicked_index = None

        if not self.pdf_files:
            self.root.config(cursor="")
            self.update_status("Nenhum PDF carregado.")
            return

        cols = 3
        row, col = 0, 0

        for path in self.pdf_files:
            try:
                doc = fitz.open(path)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir {os.path.basename(path)}:\n{e}")
                continue

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=72)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.thumbnail(self.thumbnail_size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)

                # Frame com borda configurável (tk.Frame)
                frame = tk.Frame(self.thumb_frame, highlightthickness=2,
                                 highlightbackground='#f0f0f0', relief=tk.RIDGE, borderwidth=2)
                frame.grid(row=row, column=col, padx=5, pady=5, sticky='nw')

                lbl = ttk.Label(frame, image=photo)
                lbl.image = photo
                lbl.pack()

                info = f"Pág. {page_num + 1} | {os.path.basename(path)}"
                ttk.Label(frame, text=info, font=('Arial', 8)).pack()

                # Armazena referência para manipulação posterior
                idx = len(self.thumb_widgets)
                self.thumb_widgets.append((frame, path, page_num))

                # Bind de clique simples (seleção)
                frame.bind("<Button-1>", lambda e, i=idx: self.on_thumb_click(e, i))
                lbl.bind("<Button-1>", lambda e, i=idx: self.on_thumb_click(e, i))

                # Duplo clique abre o editor da página
                lbl.bind("<Double-Button-1>", lambda e, p=path, pn=page_num: self.edit_page(p, pn))
                frame.bind("<Double-Button-1>", lambda e, p=path, pn=page_num: self.edit_page(p, pn))

                col += 1
                if col >= cols:
                    col = 0
                    row += 1

            doc.close()

        self.thumb_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.root.config(cursor="")
        self.update_status(f"{len(self.pdf_files)} PDF(s) carregados. Total de páginas: {len(self.thumb_widgets)}")

    def on_thumb_click(self, event, index):
        """Gerencia seleção com clique simples, Ctrl+click, Shift+click."""
        frame, path, page_num = self.thumb_widgets[index]
        key = (path, page_num)

        shift = event.state & 0x0001  # Shift
        ctrl = event.state & 0x0004   # Control

        if shift and self.last_clicked_index is not None:
            # Range selection: do último índice clicado até o atual
            start = min(self.last_clicked_index, index)
            end = max(self.last_clicked_index, index)
            self.selected_pages.clear()
            for i in range(start, end + 1):
                _, p, pn = self.thumb_widgets[i]
                self.selected_pages.add((p, pn))
            # Não altera last_clicked_index (âncora permanece)
        elif ctrl:
            # Alterna seleção do item clicado
            if key in self.selected_pages:
                self.selected_pages.remove(key)
            else:
                self.selected_pages.add(key)
            self.last_clicked_index = index
        else:
            # Seleção única: limpa tudo, seleciona apenas este
            self.selected_pages.clear()
            self.selected_pages.add(key)
            self.last_clicked_index = index

        self.update_all_borders()

    def update_all_borders(self):
        """Atualiza a cor da borda de todas as miniaturas conforme seleção."""
        for frame, path, page_num in self.thumb_widgets:
            if (path, page_num) in self.selected_pages:
                frame.configure(highlightbackground='red')
            else:
                frame.configure(highlightbackground='#f0f0f0')

    def edit_page(self, path, page_num):
        """Abre o editor da página em uma nova janela."""
        PDFPageEditor(self.root, path, page_num, on_save_callback=self.refresh_thumbnails)

    # ----- Seleções em lote -----
    def select_all(self):
        self.selected_pages.clear()
        for _, path, page_num in self.thumb_widgets:
            self.selected_pages.add((path, page_num))
        if self.thumb_widgets:
            self.last_clicked_index = 0
        self.update_all_borders()

    def deselect_all(self):
        self.selected_pages.clear()
        self.last_clicked_index = None
        self.update_all_borders()

    def get_selected_pages(self):
        """Retorna lista de páginas selecionadas na ordem de exibição."""
        return [(path, pn) for _, path, pn in self.thumb_widgets
                if (path, pn) in self.selected_pages]

    def get_all_pages_ordered(self):
        return [(path, pn) for _, path, pn in self.thumb_widgets]

    # ----- Operações com PDFs (inalteradas) -----
    def merge_selected(self):
        pages = self.get_selected_pages()
        if not pages:
            messagebox.showinfo("Aviso", "Nenhuma página selecionada.")
            return
        self._merge_pages(pages, "Salvar PDF unido (selecionadas)")

    def merge_all_pdfs(self):
        pages = self.get_all_pages_ordered()
        if not pages:
            messagebox.showinfo("Aviso", "Nenhum PDF carregado.")
            return
        self._merge_pages(pages, "Salvar PDF unido (todos os arquivos)")

    def extract_selected(self):
        pages = self.get_selected_pages()
        if not pages:
            messagebox.showinfo("Aviso", "Nenhuma página selecionada.")
            return
        self._merge_pages(pages, "Salvar páginas extraídas como PDF")

    def _merge_pages(self, page_list, title):
        if not page_list:
            return
        out_path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")]
        )
        if not out_path:
            return

        self.update_status("Criando PDF...")
        self.root.config(cursor="watch")
        try:
            new_doc = fitz.open()
            for path, page_num in page_list:
                src = fitz.open(path)
                new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
                src.close()
            new_doc.save(out_path)
            new_doc.close()
            self.root.config(cursor="")
            self.update_status(f"PDF salvo: {os.path.basename(out_path)}")
            messagebox.showinfo("Sucesso", f"Arquivo criado:\n{out_path}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Erro", f"Falha ao gerar PDF:\n{e}")

    def split_pdfs(self):
        if not self.pdf_files:
            messagebox.showinfo("Aviso", "Nenhum PDF carregado.")
            return
        out_dir = filedialog.askdirectory(title="Pasta para salvar páginas divididas")
        if not out_dir:
            return

        self.update_status("Dividindo PDFs...")
        self.root.config(cursor="watch")
        try:
            for path in self.pdf_files:
                base = os.path.splitext(os.path.basename(path))[0]
                doc = fitz.open(path)
                for i in range(len(doc)):
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=i, to_page=i)
                    out_name = f"{base}_pag_{i + 1}.pdf"
                    new_doc.save(os.path.join(out_dir, out_name))
                    new_doc.close()
                doc.close()
            self.root.config(cursor="")
            self.update_status("Divisão concluída.")
            messagebox.showinfo("Sucesso", f"Páginas salvas em:\n{out_dir}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Erro", f"Falha na divisão:\n{e}")


def main():
    root = tk.Tk()
    app = PDFManager(root)
    root.mainloop()

if __name__ == "__main__":
    main()
