import sys
import os
import time
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QListWidget, QListWidgetItem, QTabWidget,
                             QFileDialog, QMessageBox, QSplitter, QGraphicsView, QGraphicsScene,
                             QGraphicsTextItem, QGraphicsRectItem, QInputDialog, QLineEdit, QGroupBox, QSpinBox,
                             QAbstractItemView, QDialog, QComboBox, QFontComboBox, QSplashScreen, QProgressDialog,
                             QCheckBox, QSlider, QFormLayout, QDialogButtonBox)
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QIcon, QPainter, QFontMetrics, QPen, QBrush
from PyQt5.QtCore import Qt, QSize, QRectF, QBuffer, QIODevice, QByteArray
from collections import defaultdict

# ======================================================================
# Estilo Moderno (QSS)
# ======================================================================
MODERN_STYLE = """
QMainWindow { background-color: #f3f3f3; }
QTabWidget::pane { border: 1px solid #e0e0e0; background: white; border-radius: 4px; }
QTabBar::tab { background: #f3f3f3; border: 1px solid #e0e0e0; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: bold; color: #005A9E; }
QPushButton { background-color: #005A9E; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background-color: #0078D4; }
QPushButton:pressed { background-color: #004578; }
QPushButton:checked { background-color: #002240; border: 2px solid #5599FF; }
QListWidget { background-color: white; border: 1px solid #e0e0e0; border-radius: 4px; outline: none; }
QListWidget::item { padding: 5px; }
QListWidget::item:selected { background-color: #cce8ff; color: black; border-radius: 4px; }
QLineEdit, QSpinBox, QComboBox, QFontComboBox { border: 1px solid #ccc; padding: 5px; border-radius: 3px; background: white; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QFontComboBox:focus { border: 1px solid #0078D4; }
QGroupBox { font-weight: bold; border: 1px solid #d0d0d0; border-radius: 5px; margin-top: 2ex; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; color: #555; }
"""


# ======================================================================
# Utilitário para parsear Ranges
# ======================================================================
def parse_page_range(range_str, max_pages):
    pages = set()
    range_str = range_str.replace(',', ';')
    parts = range_str.split(';')

    for part in parts:
        part = part.strip()
        if not part: continue
        if '-' in part:
            try:
                start, end = part.split('-', 1)
                s = max(1, int(start.strip()))
                e = min(max_pages, int(end.strip()))
                if s <= e: pages.update(range(s - 1, e))
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages: pages.add(p - 1)
            except ValueError:
                pass
    return sorted(list(pages))


# ======================================================================
# Classes de UI Auxiliares e Diálogos
# ======================================================================
class InteractiveGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.start_pos = None
        self.current_rect_item = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = self.mapToScene(event.pos())
            if self.current_rect_item:
                self.scene().removeItem(self.current_rect_item)
            self.current_rect_item = QGraphicsRectItem()
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(2)
            self.current_rect_item.setPen(pen)
            self.current_rect_item.setBrush(QBrush(QColor(0, 0, 0, 150)))
            self.scene().addItem(self.current_rect_item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start_pos and self.current_rect_item:
            end_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, end_pos).normalized()
            self.current_rect_item.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = None
        super().mouseReleaseEvent(event)


# ======================================================================
# View para múltiplos retângulos de redação (mantém todos os rects)
# ======================================================================
class MultiRedactGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.start_pos = None
        self.current_rect_item = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = self.mapToScene(event.pos())
            # Cria novo retângulo SEM remover os anteriores
            self.current_rect_item = QGraphicsRectItem()
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(2)
            self.current_rect_item.setPen(pen)
            self.current_rect_item.setBrush(QBrush(QColor(0, 0, 0, 220)))
            self.scene().addItem(self.current_rect_item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start_pos and self.current_rect_item:
            end_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, end_pos).normalized()
            self.current_rect_item.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = None
        super().mouseReleaseEvent(event)


# ======================================================================
# Diálogo de Redação (Remover Conteúdo Confidencial)
# ======================================================================
class RedactionDialog(QDialog):
    def __init__(self, parent, pdf_path, page_num):
        super().__init__(parent)
        self.setWindowTitle(f"Redação – Página {page_num + 1} de {os.path.basename(pdf_path)}")
        self.resize(950, 750)
        self.setStyleSheet(MODERN_STYLE)

        self.pdf_path = pdf_path
        self.page_num = page_num
        self.scale = 1.5

        self.doc = fitz.open(pdf_path)
        self.page = self.doc.load_page(page_num)

        layout = QVBoxLayout(self)

        info = QLabel("🖱  Clique e arraste para marcar áreas confidenciais (preto). "
                      "Você pode desenhar várias áreas. Clique em 'Aplicar Redação' para remover permanentemente.")
        info.setStyleSheet("color: #A00000; font-weight: bold; padding: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.scene = QGraphicsScene(self)
        self.view = MultiRedactGraphicsView(self.scene)
        layout.addWidget(self.view)

        btn_layout = QHBoxLayout()
        btn_undo = QPushButton("Desfazer Última Área")
        btn_undo.setStyleSheet("background-color: #555;")
        btn_undo.clicked.connect(self.undo_last_rect)

        btn_apply = QPushButton("✔  Aplicar Redação")
        btn_apply.setStyleSheet("background-color: #A00000;")
        btn_apply.clicked.connect(self.apply_redaction)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_undo)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.load_page()

    def load_page(self):
        mat = fitz.Matrix(self.scale, self.scale)
        pix = self.page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self.scene.addPixmap(QPixmap.fromImage(img))
        self.scene.setSceneRect(QRectF(0, 0, pix.width, pix.height))

    def get_rect_items(self):
        return [item for item in self.scene.items() if isinstance(item, QGraphicsRectItem)]

    def undo_last_rect(self):
        rects = self.get_rect_items()
        if rects:
            self.scene.removeItem(rects[0])  # items() retorna em ordem inversa de inserção

    def apply_redaction(self):
        rects = self.get_rect_items()
        if not rects:
            QMessageBox.warning(self, "Aviso", "Desenhe pelo menos uma área para redação.")
            return

        reply = QMessageBox.question(
            self, "Confirmar",
            f"Tem certeza que deseja remover permanentemente {len(rects)} área(s)?\n"
            "Esta ação não pode ser desfeita!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            for rect_item in rects:
                r = rect_item.rect()
                pdf_rect = fitz.Rect(
                    r.x() / self.scale,
                    r.y() / self.scale,
                    (r.x() + r.width()) / self.scale,
                    (r.y() + r.height()) / self.scale
                )
                self.page.add_redact_annot(pdf_rect, fill=(0, 0, 0))

            self.page.apply_redactions()
            self.doc.save(self.pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            self.doc.close()
            QMessageBox.information(self, "Sucesso", "Redação aplicada e salva com sucesso!")
            self.accept()
        except Exception as e:
            self.doc.close()
            QMessageBox.critical(self, "Erro", f"Falha ao aplicar redação:\n{e}")


# ======================================================================
# Classe customizada para evitar o crash do botão direito
# ======================================================================
class CustomGraphicsTextItem(QGraphicsTextItem):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)

    def contextMenuEvent(self, event):
        event.accept()


# ======================================================================
# Janela "Sobre o Desenvolvedor"
# ======================================================================
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sobre o Desenvolvedor")
        self.resize(400, 350)
        self.setStyleSheet(MODERN_STYLE)

        layout = QVBoxLayout(self)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)

        logo_path = "icon.png"
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            self.logo_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo_label.setText("[ Insira sua logo aqui ]\n(Salve a imagem como 'icon.png' na pasta do script)")
            self.logo_label.setStyleSheet("color: gray; font-style: italic;")

        layout.addWidget(self.logo_label)

        info_text = (
            "<h2 style='text-align:center;'>Luiz Perfeito</h2>"
            "<p style='text-align:center;'><b>Gerador de PDF do Perfeito</b></p>"
            "<p style='text-align:center;'>Versão: 1.0</p>"
            "<br>"
            "<p style='text-align:center;'>Completamente gratuito e open-source,<br>"
            "instagram: @phillipeknupp</p>"
        )
        self.info_label = QLabel(info_text)
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        btn_close.setFixedWidth(100)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


# ======================================================================
# Editor de uma página do PDF
# ======================================================================
class PDFPageEditor(QDialog):
    def __init__(self, parent, pdf_path, page_num, on_save_callback=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editando página {page_num + 1} – {os.path.basename(pdf_path)}")
        self.resize(1000, 750)

        self.pdf_path = pdf_path
        self.page_num = page_num
        self.on_save_callback = on_save_callback

        self.doc = fitz.open(pdf_path)
        self.page = self.doc.load_page(page_num)
        self.scale = 2.0
        self.is_updating_ui = False

        self.setup_ui()
        self.load_page()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        btn_add_text = QPushButton("Adicionar Texto Livre")
        btn_add_text.clicked.connect(self.add_text_box)

        btn_remove_text = QPushButton("Remover Texto")
        btn_remove_text.setStyleSheet("background-color: #A00000;")
        btn_remove_text.clicked.connect(self.remove_selected_text)

        btn_save_orig = QPushButton("Salvar no Original")
        btn_save_orig.clicked.connect(lambda: self.save(overwrite=True))
        btn_save_as = QPushButton("Salvar Como...")
        btn_save_as.clicked.connect(lambda: self.save(overwrite=False))

        toolbar.addWidget(btn_add_text)
        toolbar.addWidget(btn_remove_text)
        toolbar.addStretch()
        toolbar.addWidget(btn_save_orig)
        toolbar.addWidget(btn_save_as)
        layout.addLayout(toolbar)

        format_toolbar = QHBoxLayout()
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self.apply_text_format)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 150)
        self.size_spin.setValue(14)
        self.size_spin.valueChanged.connect(self.apply_text_format)

        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFixedWidth(30)
        self.btn_bold.clicked.connect(self.apply_text_format)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style: italic;")
        self.btn_italic.setFixedWidth(30)
        self.btn_italic.clicked.connect(self.apply_text_format)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setStyleSheet("text-decoration: underline;")
        self.btn_underline.setFixedWidth(30)
        self.btn_underline.clicked.connect(self.apply_text_format)

        format_toolbar.addWidget(QLabel("Fonte:"))
        format_toolbar.addWidget(self.font_combo)
        format_toolbar.addWidget(QLabel("Tamanho:"))
        format_toolbar.addWidget(self.size_spin)
        format_toolbar.addWidget(self.btn_bold)
        format_toolbar.addWidget(self.btn_italic)
        format_toolbar.addWidget(self.btn_underline)
        format_toolbar.addStretch()

        layout.addLayout(format_toolbar)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.view)
        self.scene.selectionChanged.connect(self.on_selection_changed)

    def load_page(self):
        mat = fitz.Matrix(self.scale, self.scale)
        pix = self.page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self.pixmap_item = self.scene.addPixmap(QPixmap.fromImage(img))
        self.scene.setSceneRect(QRectF(self.pixmap_item.pixmap().rect()))

    def get_current_font(self):
        font = self.font_combo.currentFont()
        font.setPointSize(self.size_spin.value())
        font.setBold(self.btn_bold.isChecked())
        font.setItalic(self.btn_italic.isChecked())
        font.setUnderline(self.btn_underline.isChecked())
        return font

    def apply_text_format(self):
        if getattr(self, 'is_updating_ui', False): return
        font = self.get_current_font()
        for item in self.scene.selectedItems():
            if isinstance(item, QGraphicsTextItem):
                item.setFont(font)

    def on_selection_changed(self):
        items = self.scene.selectedItems()
        if len(items) == 1 and isinstance(items[0], QGraphicsTextItem):
            self.is_updating_ui = True
            font = items[0].font()
            self.font_combo.setCurrentFont(font)
            self.size_spin.setValue(font.pointSize())
            self.btn_bold.setChecked(font.bold())
            self.btn_italic.setChecked(font.italic())
            self.btn_underline.setChecked(font.underline())
            self.is_updating_ui = False

    def add_text_box(self):
        text_item = CustomGraphicsTextItem("Digite seu texto aqui...")
        text_item.setDefaultTextColor(QColor("black"))
        text_item.setFont(self.get_current_font())
        text_item.setFlags(
            QGraphicsTextItem.ItemIsSelectable | QGraphicsTextItem.ItemIsMovable | QGraphicsTextItem.ItemIsFocusable)
        text_item.setTextInteractionFlags(Qt.TextEditorInteraction)

        rect = self.view.viewport().rect()
        scene_pos = self.view.mapToScene(rect.center())
        text_item.setPos(scene_pos)
        self.scene.addItem(text_item)
        self.scene.clearSelection()
        text_item.setSelected(True)
        text_item.setFocus()

    def remove_selected_text(self):
        for item in self.scene.selectedItems():
            if isinstance(item, QGraphicsTextItem):
                self.scene.removeItem(item)

    def save(self, overwrite=True):
        progress = QProgressDialog("Salvando alterações no PDF...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            for item in self.scene.items():
                if isinstance(item, QGraphicsTextItem):
                    text = item.toPlainText().strip()
                    if not text: continue

                    pos = item.scenePos()
                    pdf_x = pos.x() / self.scale
                    pdf_y = pos.y() / self.scale

                    font = item.font()
                    size = font.pointSize()
                    family = font.family().lower()
                    base_font = "ti" if ("times" in family or "serif" in family) else (
                        "co" if "courier" in family or "mono" in family else "he")

                    font_map = {"ti": ["tiro", "tibo", "tiit", "tibi"], "co": ["cour", "cobo", "coit", "cobi"],
                                "he": ["helv", "hebo", "heit", "hebi"]}
                    idx = (1 if font.bold() else 0) + (2 if font.italic() else 0)
                    fitz_font = font_map[base_font][idx]

                    self.page.insert_font(fontname=fitz_font, fontbuffer=None)
                    y_offset = pdf_y + (size * 0.9) + (4 / self.scale)
                    x_offset = pdf_x + (4 / self.scale)

                    for line in text.split('\n'):
                        text_len = fitz.get_text_length(line, fontname=fitz_font, fontsize=size)
                        self.page.insert_text(fitz.Point(x_offset, y_offset), line, fontname=fitz_font, fontsize=size,
                                              color=(0, 0, 0))

                        if font.underline():
                            p1 = fitz.Point(x_offset, y_offset + size * 0.1)
                            p2 = fitz.Point(x_offset + text_len, y_offset + size * 0.1)
                            self.page.draw_line(p1, p2, color=(0, 0, 0), width=max(0.5, size * 0.05))
                        y_offset += size * 1.2

            if overwrite:
                self.doc.save(self.pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                msg = "PDF original atualizado com sucesso."
            else:
                new_path, _ = QFileDialog.getSaveFileName(self, "Salvar Como", "", "PDF Files (*.pdf)")
                if not new_path:
                    progress.close()
                    return
                self.doc.save(new_path, garbage=3, deflate=True)
                msg = f"PDF salvo em:\n{new_path}"

            self.doc.close()
            progress.close()
            QMessageBox.information(self, "Sucesso", msg)
            if self.on_save_callback: self.on_save_callback()
            self.accept()
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Falha ao salvar:\n{e}")


# ======================================================================
# Aplicação Principal
# ======================================================================
class PDFManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerador de PDF do Perfeito")

        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1300, 800)
        self.setStyleSheet(MODERN_STYLE)
        self.setAcceptDrops(True)

        self.pdf_files = []
        self.thumbnail_cache = {}

        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.setup_tab_home()
        self.setup_tab_pages()
        self.setup_tab_general()

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        self.thumb_list = QListWidget()
        self.thumb_list.setViewMode(QListWidget.IconMode)
        self.thumb_list.setFlow(QListWidget.LeftToRight)
        self.thumb_list.setWrapping(True)
        self.thumb_list.setResizeMode(QListWidget.Adjust)
        self.thumb_list.setSpacing(10)
        self.thumb_list.setIconSize(QSize(160, 220))
        self.thumb_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.thumb_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.thumb_list.setDefaultDropAction(Qt.MoveAction)
        self.thumb_list.setAcceptDrops(True)
        self.thumb_list.setDragEnabled(True)
        self.thumb_list.setDropIndicatorShown(True)
        self.thumb_list.itemDoubleClicked.connect(self.on_thumb_double_click)
        splitter.addWidget(self.thumb_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("PDFs Inseridos (Arraste arquivos aqui):"))

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        right_layout.addWidget(self.file_list)
        splitter.addWidget(right_panel)

        splitter.setSizes([900, 300])
        self.statusBar().showMessage("Pronto. Arraste PDFs para começar.")

    def setup_tab_home(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        group = QGroupBox("Arquivos")
        glayout = QHBoxLayout(group)

        btn_add = QPushButton("Adicionar PDF")
        btn_add.clicked.connect(self.add_pdf)
        btn_remove = QPushButton("Remover Selecionados")
        btn_remove.clicked.connect(self.remove_pdf)
        btn_clear = QPushButton("Limpar Tudo")
        btn_clear.clicked.connect(self.clear_all)

        glayout.addWidget(btn_add)
        glayout.addWidget(btn_remove)
        glayout.addWidget(btn_clear)
        layout.addWidget(group)

        group_about = QGroupBox("Informações")
        about_layout = QHBoxLayout(group_about)
        btn_about = QPushButton("Sobre o Desenvolvedor")
        btn_about.clicked.connect(self.show_about_dialog)
        about_layout.addWidget(btn_about)
        layout.addWidget(group_about)

        layout.addStretch()
        self.tabs.addTab(tab, " Início ")

    def show_about_dialog(self):
        about = AboutDialog(self)
        about.exec_()

    def setup_tab_pages(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        grp_manual = QGroupBox("Ações com Miniaturas Selecionadas")
        l_manual = QHBoxLayout(grp_manual)

        btn_merge_sel = QPushButton("Unir")
        btn_merge_sel.clicked.connect(self.merge_selected)
        btn_ext_sel = QPushButton("Extrair")
        btn_ext_sel.clicked.connect(self.extract_selected)

        btn_to_img = QPushButton("Para Imagem")
        btn_to_img.clicked.connect(self.pdf_to_images)
        btn_rotate = QPushButton("Rotacionar")
        btn_rotate.clicked.connect(self.rotate_selected)
        btn_watermark = QPushButton("Marca D'água")
        btn_watermark.clicked.connect(self.add_watermark_to_selected)

        btn_redact = QPushButton("Remover Confidencial")
        btn_redact.setStyleSheet("background-color: #A00000;")
        btn_redact.clicked.connect(self.apply_redaction)

        btn_ocr = QPushButton("Fazer OCR")
        btn_ocr.setStyleSheet("background-color: #008000;")
        btn_ocr.clicked.connect(self.apply_ocr)

        for btn in [btn_merge_sel, btn_ext_sel, btn_to_img, btn_rotate, btn_watermark, btn_redact, btn_ocr]:
            l_manual.addWidget(btn)
        layout.addWidget(grp_manual)

        grp_range = QGroupBox("Extração por Intervalo")
        l_range = QHBoxLayout(grp_range)

        self.inp_range = QLineEdit()
        self.inp_range.setPlaceholderText("Ex: 1-5; 8")
        self.inp_range.setFixedWidth(100)
        btn_ext_range = QPushButton("Extrair")
        btn_ext_range.clicked.connect(self.extract_by_range)

        l_range.addWidget(QLabel("Pág:"))
        l_range.addWidget(self.inp_range)
        l_range.addWidget(btn_ext_range)
        layout.addWidget(grp_range)
        layout.addStretch()
        self.tabs.addTab(tab, " Páginas ")

    def setup_tab_general(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        grp_global = QGroupBox("Operações Globais")
        l_global = QHBoxLayout(grp_global)

        btn_merge_all = QPushButton("Unir Todos")
        btn_merge_all.clicked.connect(self.merge_all_pdfs)
        btn_compress = QPushButton("Comprimir PDFs")
        btn_compress.clicked.connect(self.compress_pdfs)
        btn_img_pdf = QPushButton("Imagens para PDF")
        btn_img_pdf.clicked.connect(self.images_to_pdf)

        for btn in [btn_merge_all, btn_compress, btn_img_pdf]:
            l_global.addWidget(btn)
        layout.addWidget(grp_global)

        grp_sec = QGroupBox("Segurança")
        l_sec = QHBoxLayout(grp_sec)
        btn_unlock = QPushButton("Desbloquear")
        btn_unlock.clicked.connect(self.unlock_pdf)
        btn_lock = QPushButton("Proteger")
        btn_lock.clicked.connect(self.lock_pdf)

        l_sec.addWidget(btn_unlock)
        l_sec.addWidget(btn_lock)
        layout.addWidget(grp_sec)
        layout.addStretch()
        self.tabs.addTab(tab, " Geral ")

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        added = False
        for f in files:
            if f.lower().endswith('.pdf') and f not in self.pdf_files:
                self.pdf_files.append(f)
                self.file_list.addItem(os.path.basename(f))
                added = True
        if added: self.refresh_thumbnails()

    # ------------------------------------------------------------------
    # Gerenciamento de arquivos
    # ------------------------------------------------------------------
    def add_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Selecionar PDF", "", "PDF Files (*.pdf)")
        added = False
        for f in files:
            if f not in self.pdf_files:
                self.pdf_files.append(f)
                self.file_list.addItem(os.path.basename(f))
                added = True
        if added: self.refresh_thumbnails()

    def remove_pdf(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items: return
        for item in selected_items:
            row = self.file_list.row(item)
            del self.pdf_files[row]
            self.file_list.takeItem(row)
        self.refresh_thumbnails()

    def clear_all(self):
        self.pdf_files.clear()
        self.file_list.clear()
        self.thumb_list.clear()
        self.thumbnail_cache.clear()
        self.statusBar().showMessage("Tudo limpo.")

    def refresh_thumbnails(self):
        total_pages = 0
        docs_to_process = []
        for path in self.pdf_files:
            try:
                doc = fitz.open(path)
                total_pages += len(doc)
                docs_to_process.append((path, doc))
            except:
                pass

        if total_pages == 0: return

        progress = QProgressDialog("Gerando miniaturas...", "Cancelar", 0, total_pages, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        self.thumb_list.clear()
        current_step = 0

        for path, doc in docs_to_process:
            filename = os.path.basename(path)
            for page_num in range(len(doc)):
                if progress.wasCanceled():
                    break

                cache_key = f"{path}_{page_num}"
                if cache_key not in self.thumbnail_cache:
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(dpi=50)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    self.thumbnail_cache[cache_key] = QPixmap.fromImage(img)

                item = QListWidgetItem()
                item.setIcon(QIcon(self.thumbnail_cache[cache_key]))
                item.setText(f"Página {page_num + 1}\n{filename[:12]}...")
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
                item.setData(Qt.UserRole, (path, page_num))
                self.thumb_list.addItem(item)

                current_step += 1
                progress.setValue(current_step)
                QApplication.processEvents()

            doc.close()
            if progress.wasCanceled(): break

        progress.close()
        self.statusBar().showMessage(f"{len(self.pdf_files)} PDF(s) carregados.")

    def on_thumb_double_click(self, item):
        path, page_num = item.data(Qt.UserRole)
        editor = PDFPageEditor(self, path, page_num, on_save_callback=self.refresh_thumbnail_single)
        editor.exec_()

    def refresh_thumbnail_single(self):
        self.thumbnail_cache.clear()
        self.refresh_thumbnails()

    def get_selected_pages_from_thumbs(self):
        return [item.data(Qt.UserRole) for item in self.thumb_list.selectedItems()]

    def get_all_pages_ordered(self):
        return [self.thumb_list.item(i).data(Qt.UserRole) for i in range(self.thumb_list.count())]

    # ------------------------------------------------------------------
    # Mesclar / Extrair
    # ------------------------------------------------------------------
    def _merge_pages(self, page_list, title):
        if not page_list:
            QMessageBox.warning(self, "Aviso", "Nenhuma página selecionada.")
            return
        out_path, _ = QFileDialog.getSaveFileName(self, title, "", "PDF Files (*.pdf)")
        if not out_path: return

        progress = QProgressDialog("Mesclando páginas...", None, 0, 0, self)
        progress.setWindowTitle("Processando")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            new_doc = fitz.open()
            for path, page_num in page_list:
                src = fitz.open(path)
                new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
                src.close()
                QApplication.processEvents()

            new_doc.save(out_path)
            new_doc.close()
            progress.close()
            QMessageBox.information(self, "Sucesso", f"Salvo em:\n{out_path}")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Ocorreu um erro:\n{e}")

    def merge_selected(self):
        self._merge_pages(self.get_selected_pages_from_thumbs(), "Salvar PDF (Selecionadas)")

    def extract_selected(self):
        self._merge_pages(self.get_selected_pages_from_thumbs(), "Salvar Extraídas")

    def merge_all_pdfs(self):
        self._merge_pages(self.get_all_pages_ordered(), "Salvar PDF (Todos na ordem atual)")

    def extract_by_range(self):
        if not self.pdf_files:
            QMessageBox.warning(self, "Aviso", "Adicione um PDF primeiro.")
            return

        target_pdf = self.pdf_files[0]
        range_text = self.inp_range.text()

        if not range_text:
            QMessageBox.warning(self, "Aviso", "Digite o intervalo (ex: 1-5; 8).")
            return

        doc = fitz.open(target_pdf)
        pages_to_extract = parse_page_range(range_text, len(doc))

        if not pages_to_extract:
            doc.close()
            QMessageBox.warning(self, "Aviso", "Nenhuma página válida no intervalo inserido.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Salvar Extração", "", "PDF Files (*.pdf)")
        if not out_path:
            doc.close()
            return

        progress = QProgressDialog("Extraindo intervalo...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            new_doc = fitz.open()
            for p in pages_to_extract:
                new_doc.insert_pdf(doc, from_page=p, to_page=p)
            new_doc.save(out_path)
            new_doc.close()
            doc.close()
            progress.close()
            QMessageBox.information(self, "Sucesso", "Intervalo extraído com sucesso!")
        except Exception as e:
            progress.close()
            doc.close()
            QMessageBox.critical(self, "Erro", f"Ocorreu um erro ao extrair:\n{e}")

    # ------------------------------------------------------------------
    # ✅ PDF para Imagens
    # ------------------------------------------------------------------
    def pdf_to_images(self):
        selected = self.get_selected_pages_from_thumbs()
        if not selected:
            QMessageBox.warning(self, "Aviso",
                                "Selecione pelo menos uma página nas miniaturas.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Destino")
        if not out_dir:
            return

        fmt, ok = QInputDialog.getItem(
            self, "Formato de Imagem", "Escolha o formato:",
            ["PNG", "JPG", "BMP", "TIFF"], 0, False
        )
        if not ok:
            return

        dpi_str, ok = QInputDialog.getItem(
            self, "Resolução (DPI)", "Escolha a qualidade:",
            ["72 dpi (baixa)", "150 dpi (média)", "300 dpi (alta)", "600 dpi (máxima)"],
            1, False
        )
        if not ok:
            return
        dpi = int(dpi_str.split()[0])

        progress = QProgressDialog("Convertendo para imagens...", "Cancelar", 0, len(selected), self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            for i, (path, page_num) in enumerate(selected):
                if progress.wasCanceled():
                    break
                doc = fitz.open(path)
                page = doc.load_page(page_num)
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                base = os.path.splitext(os.path.basename(path))[0]
                out_file = os.path.join(out_dir, f"{base}_pag{page_num + 1}.{fmt.lower()}")
                pix.save(out_file)
                doc.close()
                progress.setValue(i + 1)
                QApplication.processEvents()

            progress.close()
            QMessageBox.information(self, "Sucesso",
                                    f"{len(selected)} imagem(ns) salva(s) em:\n{out_dir}")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao converter para imagem:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Rotacionar páginas selecionadas
    # ------------------------------------------------------------------
    def rotate_selected(self):
        selected = self.get_selected_pages_from_thumbs()
        if not selected:
            QMessageBox.warning(self, "Aviso",
                                "Selecione pelo menos uma página nas miniaturas.")
            return

        angle_label, ok = QInputDialog.getItem(
            self, "Rotacionar Página",
            "Escolha o ângulo de rotação:",
            ["90° (Direita)", "180°", "270° (Esquerda / -90°)"],
            0, False
        )
        if not ok:
            return

        angle_map = {
            "90° (Direita)": 90,
            "180°": 180,
            "270° (Esquerda / -90°)": 270
        }
        rotation = angle_map[angle_label]

        # Agrupar páginas por arquivo
        pages_by_file = defaultdict(list)
        for path, page_num in selected:
            pages_by_file[path].append(page_num)

        progress = QProgressDialog("Rotacionando páginas...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            for path, page_nums in pages_by_file.items():
                doc = fitz.open(path)
                for pn in page_nums:
                    page = doc.load_page(pn)
                    new_rot = (page.rotation + rotation) % 360
                    page.set_rotation(new_rot)
                doc.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                doc.close()

            progress.close()
            self.thumbnail_cache.clear()
            self.refresh_thumbnails()
            QMessageBox.information(self, "Sucesso",
                                    f"{len(selected)} página(s) rotacionada(s) com sucesso!")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao rotacionar:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Marca D'água nas páginas selecionadas
    # ------------------------------------------------------------------
    def add_watermark_to_selected(self):
        selected = self.get_selected_pages_from_thumbs()
        if not selected:
            QMessageBox.warning(self, "Aviso",
                                "Selecione pelo menos uma página nas miniaturas.")
            return

        text, ok = QInputDialog.getText(
            self, "Marca D'água",
            "Digite o texto da marca d'água:"
        )
        if not ok or not text.strip():
            return

        opacity_label, ok = QInputDialog.getItem(
            self, "Opacidade", "Escolha a opacidade da marca:",
            ["Leve (20%)", "Média (40%)", "Forte (60%)"],
            1, False
        )
        if not ok:
            return
        opacity_map = {"Leve (20%)": 0.20, "Média (40%)": 0.40, "Forte (60%)": 0.60}
        opacity = opacity_map[opacity_label]

        pages_by_file = defaultdict(list)
        for path, page_num in selected:
            pages_by_file[path].append(page_num)

        progress = QProgressDialog("Adicionando marca d'água...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            for path, page_nums in pages_by_file.items():
                doc = fitz.open(path)
                for pn in page_nums:
                    page = doc.load_page(pn)
                    rect = page.rect
                    # Centralizar e inclinar 45°
                    fontsize = min(rect.width, rect.height) / 10
                    color = (0.5, 0.5, 0.5)

                    # Insere watermark em múltiplas posições para cobrir a página
                    positions = [
                        fitz.Point(rect.width * 0.25, rect.height * 0.35),
                        fitz.Point(rect.width * 0.15, rect.height * 0.65),
                        fitz.Point(rect.width * 0.55, rect.height * 0.55),
                    ]
                    for pos in positions:
                        page.insert_text(
                            pos,
                            text,
                            fontsize=fontsize,
                            color=color,
                            rotate=45,
                            overlay=False
                        )

                doc.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                doc.close()

            progress.close()
            self.thumbnail_cache.clear()
            self.refresh_thumbnails()
            QMessageBox.information(self, "Sucesso",
                                    f"Marca d'água adicionada a {len(selected)} página(s)!")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao adicionar marca d'água:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Remover Conteúdo Confidencial (Redação)
    # ------------------------------------------------------------------
    def apply_redaction(self):
        selected = self.get_selected_pages_from_thumbs()
        if not selected:
            QMessageBox.warning(self, "Aviso",
                                "Selecione pelo menos uma página nas miniaturas.")
            return

        if len(selected) > 1:
            reply = QMessageBox.question(
                self, "Múltiplas Páginas",
                f"Você selecionou {len(selected)} páginas.\n"
                "O editor de redação será aberto para cada uma sequencialmente.\nContinuar?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        any_saved = False
        for path, page_num in selected:
            dialog = RedactionDialog(self, path, page_num)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                any_saved = True

        if any_saved:
            self.thumbnail_cache.clear()
            self.refresh_thumbnails()

    # ------------------------------------------------------------------
    # ✅ Fazer OCR nas páginas selecionadas
    # ------------------------------------------------------------------
    def apply_ocr(self):
        selected = self.get_selected_pages_from_thumbs()
        if not selected:
            QMessageBox.warning(self, "Aviso",
                                "Selecione pelo menos uma página nas miniaturas.")
            return

        # Verifica se o Tesseract / OCR está disponível no PyMuPDF
        try:
            test_doc = fitz.open()
            test_page = test_doc.new_page()
            _ = test_page.get_textpage_ocr(language="por", full=True)
            test_doc.close()
        except Exception as ocr_err:
            err_msg = str(ocr_err).lower()
            if "tesseract" in err_msg or "ocr" in err_msg or "command" in err_msg:
                QMessageBox.critical(
                    self, "Tesseract não encontrado",
                    "O OCR requer o Tesseract instalado no sistema.\n\n"
                    "Instale em: https://github.com/tesseract-ocr/tesseract\n"
                    "Em seguida reinicie o programa."
                )
                return

        lang, ok = QInputDialog.getItem(
            self, "Idioma do OCR",
            "Escolha o idioma do documento:",
            ["por (Português)", "eng (Inglês)", "spa (Espanhol)", "fra (Francês)", "deu (Alemão)"],
            0, False
        )
        if not ok:
            return
        lang_code = lang.split()[0]

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF com Texto OCR", "", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        progress = QProgressDialog("Aplicando OCR nas páginas selecionadas...",
                                   "Cancelar", 0, len(selected), self)
        progress.setWindowTitle("OCR em andamento")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            new_doc = fitz.open()
            for i, (path, page_num) in enumerate(selected):
                if progress.wasCanceled():
                    break
                progress.setLabelText(f"Processando página {page_num + 1} de {os.path.basename(path)}...")
                QApplication.processEvents()

                src_doc = fitz.open(path)
                src_page = src_doc.load_page(page_num)

                # Renderiza a página como imagem e reabre como PDF com OCR
                mat = fitz.Matrix(2.0, 2.0)
                pix = src_page.get_pixmap(matrix=mat)
                img_pdf_bytes = pix.pdfocr_tobytes(compress=True, language=lang_code)
                img_pdf = fitz.open("pdf", img_pdf_bytes)
                new_doc.insert_pdf(img_pdf)
                img_pdf.close()
                src_doc.close()

                progress.setValue(i + 1)
                QApplication.processEvents()

            if not progress.wasCanceled():
                new_doc.save(out_path, garbage=3, deflate=True)
                progress.close()
                QMessageBox.information(
                    self, "OCR Concluído",
                    f"PDF pesquisável salvo em:\n{out_path}\n\n"
                    f"Páginas processadas: {new_doc.page_count}"
                )
            else:
                progress.close()
                QMessageBox.information(self, "Cancelado", "OCR cancelado pelo usuário.")

            new_doc.close()
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro no OCR", f"Falha ao aplicar OCR:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Comprimir PDFs
    # ------------------------------------------------------------------
    def compress_pdfs(self):
        if not self.pdf_files:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos um PDF primeiro.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Selecionar Pasta para PDFs Comprimidos")
        if not out_dir:
            return

        level_label, ok = QInputDialog.getItem(
            self, "Nível de Compressão",
            "Escolha o nível de compressão:",
            ["Leve – garbage=1", "Médio – garbage=3", "Máximo – garbage=4 + clean"],
            1, False
        )
        if not ok:
            return

        garbage = 1 if "Leve" in level_label else (3 if "Médio" in level_label else 4)
        clean = "Máximo" in level_label

        progress = QProgressDialog("Comprimindo PDFs...", "Cancelar", 0, len(self.pdf_files), self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        total_original = 0
        total_compressed = 0
        errors = []

        try:
            for i, path in enumerate(self.pdf_files):
                if progress.wasCanceled():
                    break
                progress.setLabelText(f"Comprimindo: {os.path.basename(path)}")
                QApplication.processEvents()

                try:
                    original_size = os.path.getsize(path)
                    total_original += original_size

                    doc = fitz.open(path)
                    base = os.path.basename(path)
                    out_path = os.path.join(out_dir, f"comprimido_{base}")
                    doc.save(out_path, garbage=garbage, deflate=True, clean=clean)
                    doc.close()

                    compressed_size = os.path.getsize(out_path)
                    total_compressed += compressed_size
                except Exception as e:
                    errors.append(f"{os.path.basename(path)}: {e}")

                progress.setValue(i + 1)
                QApplication.processEvents()

            progress.close()

            if total_original > 0:
                reduction = (1 - total_compressed / total_original) * 100
                msg = (f"Compressão concluída!\n\n"
                       f"Original: {total_original / 1024:.1f} KB\n"
                       f"Comprimido: {total_compressed / 1024:.1f} KB\n"
                       f"Redução: {reduction:.1f}%\n\n"
                       f"Arquivos salvos em:\n{out_dir}")
                if errors:
                    msg += f"\n\nErros:\n" + "\n".join(errors)
                QMessageBox.information(self, "Compressão Concluída", msg)

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro durante a compressão:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Imagens para PDF
    # ------------------------------------------------------------------
    def images_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Imagens", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp)"
        )
        if not files:
            return

        if len(files) > 1:
            reply = QMessageBox.question(
                self, "Ordem das Imagens",
                f"{len(files)} imagem(ns) selecionada(s).\n"
                "As imagens serão adicionadas na ordem de seleção.\nContinuar?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF Resultante", "", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        progress = QProgressDialog("Convertendo imagens para PDF...", "Cancelar",
                                   0, len(files), self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            new_doc = fitz.open()
            for i, img_path in enumerate(files):
                if progress.wasCanceled():
                    break
                progress.setLabelText(f"Adicionando: {os.path.basename(img_path)}")
                QApplication.processEvents()

                # Abre imagem e converte para PDF de uma página
                img_doc = fitz.open(img_path)
                pdf_bytes = img_doc.convert_to_pdf()
                img_pdf = fitz.open("pdf", pdf_bytes)
                new_doc.insert_pdf(img_pdf)
                img_pdf.close()
                img_doc.close()

                progress.setValue(i + 1)
                QApplication.processEvents()

            if not progress.wasCanceled():
                new_doc.save(out_path, garbage=3, deflate=True)
                new_doc.close()
                progress.close()
                QMessageBox.information(
                    self, "Sucesso",
                    f"PDF criado com {len(files)} página(s):\n{out_path}"
                )
            else:
                new_doc.close()
                progress.close()

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao converter imagens:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Desbloquear PDF (remover senha)
    # ------------------------------------------------------------------
    def unlock_pdf(self):
        if not self.pdf_files:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos um PDF primeiro.")
            return

        items = [os.path.basename(f) for f in self.pdf_files]
        item_name, ok = QInputDialog.getItem(
            self, "Desbloquear PDF",
            "Selecione o PDF protegido:", items, 0, False
        )
        if not ok:
            return

        idx = items.index(item_name)
        path = self.pdf_files[idx]

        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o arquivo:\n{e}")
            return

        if not doc.is_encrypted:
            doc.close()
            QMessageBox.information(self, "Informação",
                                    "Este PDF não está protegido por senha.")
            return

        password, ok = QInputDialog.getText(
            self, "Senha do PDF",
            f"Digite a senha de '{item_name}':",
            QLineEdit.Password
        )
        if not ok:
            doc.close()
            return

        if not doc.authenticate(password):
            doc.close()
            QMessageBox.critical(self, "Erro", "Senha incorreta! Não foi possível desbloquear o PDF.")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF Desbloqueado", "", "PDF Files (*.pdf)"
        )
        if not out_path:
            doc.close()
            return

        progress = QProgressDialog("Removendo proteção...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            doc.save(out_path, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            doc.close()
            progress.close()
            QMessageBox.information(self, "Sucesso",
                                    f"PDF desbloqueado salvo em:\n{out_path}")
        except Exception as e:
            doc.close()
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao salvar PDF desbloqueado:\n{e}")

    # ------------------------------------------------------------------
    # ✅ Proteger PDF (adicionar senha)
    # ------------------------------------------------------------------
    def lock_pdf(self):
        if not self.pdf_files:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos um PDF primeiro.")
            return

        items = [os.path.basename(f) for f in self.pdf_files]
        item_name, ok = QInputDialog.getItem(
            self, "Proteger PDF",
            "Selecione o PDF para proteger:", items, 0, False
        )
        if not ok:
            return

        idx = items.index(item_name)
        path = self.pdf_files[idx]

        # Diálogo personalizado para senha com confirmação
        dialog = QDialog(self)
        dialog.setWindowTitle("Definir Senha de Proteção")
        dialog.setStyleSheet(MODERN_STYLE)
        dialog.setFixedSize(380, 220)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        inp_pwd = QLineEdit()
        inp_pwd.setEchoMode(QLineEdit.Password)
        inp_pwd.setPlaceholderText("Mínimo 4 caracteres")

        inp_confirm = QLineEdit()
        inp_confirm.setEchoMode(QLineEdit.Password)
        inp_confirm.setPlaceholderText("Repita a senha")

        form.addRow("Nova Senha:", inp_pwd)
        form.addRow("Confirmar Senha:", inp_confirm)
        layout.addLayout(form)

        # Permissões
        chk_print = QCheckBox("Permitir Impressão")
        chk_print.setChecked(True)
        chk_copy = QCheckBox("Permitir Copiar Texto")
        chk_copy.setChecked(False)
        layout.addWidget(chk_print)
        layout.addWidget(chk_copy)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        if dialog.exec_() != QDialog.Accepted:
            return

        password = inp_pwd.text()
        confirm = inp_confirm.text()

        if not password:
            QMessageBox.warning(self, "Aviso", "A senha não pode ser vazia.")
            return
        if len(password) < 4:
            QMessageBox.warning(self, "Aviso", "A senha deve ter pelo menos 4 caracteres.")
            return
        if password != confirm:
            QMessageBox.warning(self, "Aviso", "As senhas não coincidem!")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF Protegido", "", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        progress = QProgressDialog("Aplicando proteção...", None, 0, 0, self)
        progress.setWindowTitle("Aguarde")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        try:
            # Monta permissões
            permissions = 0
            if chk_print.isChecked():
                permissions |= fitz.PDF_PERM_PRINT
            if chk_copy.isChecked():
                permissions |= fitz.PDF_PERM_COPY

            doc = fitz.open(path)
            # Se já estiver criptografado, autentica primeiro
            if doc.is_encrypted:
                pwd_orig, ok_orig = QInputDialog.getText(
                    self, "Senha Atual",
                    "Este PDF já tem senha. Digite a senha atual para continuar:",
                    QLineEdit.Password
                )
                if not ok_orig or not doc.authenticate(pwd_orig):
                    doc.close()
                    progress.close()
                    QMessageBox.critical(self, "Erro", "Senha atual incorreta.")
                    return

            doc.save(
                out_path,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=password + "_owner",
                permissions=permissions,
                garbage=3,
                deflate=True
            )
            doc.close()
            progress.close()
            QMessageBox.information(
                self, "Sucesso",
                f"PDF protegido com senha salvo em:\n{out_path}\n\n"
                "Guarde a senha em local seguro!"
            )
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Erro", f"Erro ao proteger PDF:\n{e}")


# ======================================================================
# Entry Point
# ======================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    splash_path = "splash.png"
    if os.path.exists(splash_path):
        try:
            splash_pix = QPixmap(splash_path)
            splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
            splash.show()
            app.processEvents()
            splash.showMessage("Carregando...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            time.sleep(1)
        except Exception as e:
            print(f"Erro ao carregar splash: {e}")
            splash = None
    else:
        splash = None

    window = PDFManagerApp()
    window.show()

    if splash:
        splash.finish(window)

    sys.exit(app.exec_())