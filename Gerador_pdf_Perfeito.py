from PyQt5 import QtCore, QtGui, QtWidgets
import sys
import os
import fitz  # PyMuPDF



class ThumbnailLabel(QtWidgets.QLabel):
    # Sinais para cliques com diferentes modificadores
    clicked = QtCore.pyqtSignal(int, int)
    shiftClicked = QtCore.pyqtSignal(int, int)
    ctrlClicked = QtCore.pyqtSignal(int, int)

    def __init__(self, pdf_index, page_num, parent=None):
        super().__init__(parent)
        self.pdf_index = pdf_index
        self.page_num = page_num

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                self.shiftClicked.emit(self.pdf_index, self.page_num)
            elif event.modifiers() & QtCore.Qt.ControlModifier:
                self.ctrlClicked.emit(self.pdf_index, self.page_num)
            else:
                self.clicked.emit(self.pdf_index, self.page_num)
        super().mousePressEvent(event)


class PDFSplitterApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerador de PDF do Perfeito")
        self.resize(1200, 600)

        # Estruturas internas
        self.pdf_paths = []
        self.pdf_docs = []
        self.selected_pages = []  # conjunto de páginas selecionadas para cada PDF
        self.last_selected_page = []  # última página selecionada de cada PDF
        self.thumbnail_labels = {}  # chave: (pdf_index, page_num)

        # Layout principal dividido em duas áreas (thumbnails e controles)
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)

        # Área esquerda: thumbnails com scroll
        self.left_frame = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(self.left_frame)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        left_layout.addWidget(self.scroll_area)
        main_layout.addWidget(self.left_frame, 3)

        # Área direita: lista de PDFs e botões de controle
        self.right_frame = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(self.right_frame)

        self.file_list_label = QtWidgets.QLabel("Lista de PDFs carregados")
        right_layout.addWidget(self.file_list_label)
        self.file_list_widget = QtWidgets.QListWidget()
        right_layout.addWidget(self.file_list_widget)

        # Botões
        self.load_btn = QtWidgets.QPushButton("Carregar novo PDF")
        self.load_btn.clicked.connect(self.load_pdf)
        right_layout.addWidget(self.load_btn)

        self.generate_btn = QtWidgets.QPushButton("Salvar Novo PDF")
        self.generate_btn.clicked.connect(self.generate_pdf)
        right_layout.addWidget(self.generate_btn)

        self.select_all_btn = QtWidgets.QPushButton("Selecionar Todas as páginas e Salvar")
        self.select_all_btn.clicked.connect(self.select_all_and_save)
        right_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QtWidgets.QPushButton("Desselecionar todas as páginas")
        self.deselect_all_btn.clicked.connect(self.deselect_all_pages)
        right_layout.addWidget(self.deselect_all_btn)

        self.move_up_btn = QtWidgets.QPushButton("Mover PDF para cima")
        self.move_up_btn.clicked.connect(self.move_up)
        right_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QtWidgets.QPushButton("Mover PDF para baixo")
        self.move_down_btn.clicked.connect(self.move_down)
        right_layout.addWidget(self.move_down_btn)

        self.delete_btn = QtWidgets.QPushButton("Apagar PDFs")
        self.delete_btn.clicked.connect(self.delete_pdf)
        right_layout.addWidget(self.delete_btn)

        main_layout.addWidget(self.right_frame, 1)

        # Habilita o drop de arquivos na janela principal
        self.setAcceptDrops(True)

    # Eventos de drag-and-drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.pdf'):
                self.pdf_paths.append(filepath)
                self.pdf_docs.append(fitz.open(filepath))
                self.selected_pages.append(set())
                self.last_selected_page.append(None)
        self.update_file_list()
        self.display_thumbnails()

    def load_pdf(self):
        options = QtWidgets.QFileDialog.Options()
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Selecione um PDF", "",
                                                            "PDF Files (*.pdf)", options=options)
        if filepath:
            self.pdf_paths.append(filepath)
            self.pdf_docs.append(fitz.open(filepath))
            self.selected_pages.append(set())
            self.last_selected_page.append(None)
            self.update_file_list()
            self.display_thumbnails()

    def update_file_list(self):
        self.file_list_widget.clear()
        for path in self.pdf_paths:
            self.file_list_widget.addItem(os.path.basename(path))

    def move_up(self):
        selected_items = self.file_list_widget.selectedIndexes()
        if not selected_items:
            return
        index = selected_items[0].row()
        if index == 0:
            return
        # Troca de posição nas listas internas
        self.pdf_paths[index], self.pdf_paths[index - 1] = self.pdf_paths[index - 1], self.pdf_paths[index]
        self.pdf_docs[index], self.pdf_docs[index - 1] = self.pdf_docs[index - 1], self.pdf_docs[index]
        self.selected_pages[index], self.selected_pages[index - 1] = self.selected_pages[index - 1], \
        self.selected_pages[index]
        self.last_selected_page[index], self.last_selected_page[index - 1] = self.last_selected_page[index - 1], \
        self.last_selected_page[index]
        self.update_file_list()
        self.file_list_widget.setCurrentRow(index - 1)
        self.display_thumbnails()

    def move_down(self):
        selected_items = self.file_list_widget.selectedIndexes()
        if not selected_items:
            return
        index = selected_items[0].row()
        if index >= len(self.pdf_paths) - 1:
            return
        self.pdf_paths[index], self.pdf_paths[index + 1] = self.pdf_paths[index + 1], self.pdf_paths[index]
        self.pdf_docs[index], self.pdf_docs[index + 1] = self.pdf_docs[index + 1], self.pdf_docs[index]
        self.selected_pages[index], self.selected_pages[index + 1] = self.selected_pages[index + 1], \
        self.selected_pages[index]
        self.last_selected_page[index], self.last_selected_page[index + 1] = self.last_selected_page[index + 1], \
        self.last_selected_page[index]
        self.update_file_list()
        self.file_list_widget.setCurrentRow(index + 1)
        self.display_thumbnails()

    def delete_pdf(self):
        selected_items = self.file_list_widget.selectedIndexes()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Nenhum PDF selecionado para deletar.")
            return
        indices = sorted([item.row() for item in selected_items], reverse=True)
        for index in indices:
            del self.pdf_paths[index]
            del self.pdf_docs[index]
            del self.selected_pages[index]
            del self.last_selected_page[index]
        self.update_file_list()
        self.display_thumbnails()

    def display_thumbnails(self):
        # Limpa os widgets antigos
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        self.thumbnail_labels.clear()

        # Tamanhos padrão para cada orientação
        thumb_size_portrait = (200, 280)
        thumb_size_landscape = (280, 200)

        thumbs_per_row = 5  # Número de thumbnails por linha (pode ser ajustado)

        # Para cada PDF, exibe um rótulo e os thumbnails de cada página
        for pdf_index, pdf_doc in enumerate(self.pdf_docs):
            if not pdf_doc:
                continue
            pdf_label = QtWidgets.QLabel(f"PDF {pdf_index + 1}: {os.path.basename(self.pdf_paths[pdf_index])}")
            self.scroll_layout.addWidget(pdf_label)
            grid_widget = QtWidgets.QWidget()
            grid_layout = QtWidgets.QGridLayout(grid_widget)
            grid_layout.setSpacing(2)  # Menor espaçamento para deixar as imagens mais juntas
            grid_layout.setContentsMargins(0, 0, 0, 0)
            num_pages = len(pdf_doc)
            for i in range(num_pages):
                page = pdf_doc[i]
                pix = page.get_pixmap()
                if pix.alpha:
                    fmt = QtGui.QImage.Format_RGBA8888
                else:
                    fmt = QtGui.QImage.Format_RGB888
                qimg = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)

                # Verifica a orientação da página para definir o tamanho da caixa
                if pix.width >= pix.height:
                    current_thumb_size = thumb_size_landscape
                else:
                    current_thumb_size = thumb_size_portrait

                # Escala a imagem para preencher a caixa, mantendo proporção, e realiza o crop centralizado
                scaled_qimg = qimg.scaled(current_thumb_size[0], current_thumb_size[1],
                                          QtCore.Qt.KeepAspectRatioByExpanding,
                                          QtCore.Qt.SmoothTransformation)
                scaled_qpixmap = QtGui.QPixmap.fromImage(scaled_qimg)
                x_offset = (scaled_qpixmap.width() - current_thumb_size[0]) // 2
                y_offset = (scaled_qpixmap.height() - current_thumb_size[1]) // 2
                final_pixmap = scaled_qpixmap.copy(x_offset, y_offset, current_thumb_size[0], current_thumb_size[1])

                thumb_label = ThumbnailLabel(pdf_index, i)
                thumb_label.setPixmap(final_pixmap)
                thumb_label.setFixedSize(current_thumb_size[0], current_thumb_size[1])
                thumb_label.setStyleSheet("border: 2px solid black;")
                # Conecta os sinais para os cliques
                thumb_label.clicked.connect(self.normal_toggle_page)
                thumb_label.shiftClicked.connect(self.shift_toggle_page)
                thumb_label.ctrlClicked.connect(self.ctrl_toggle_page)
                row = i // thumbs_per_row
                col = i % thumbs_per_row
                grid_layout.addWidget(thumb_label, row, col)
                self.thumbnail_labels[(pdf_index, i)] = thumb_label
            self.scroll_layout.addWidget(grid_widget)

    def update_thumbnail_borders(self, pdf_index):
        for page_num in range(len(self.pdf_docs[pdf_index])):
            label = self.thumbnail_labels.get((pdf_index, page_num))
            if label:
                if page_num in self.selected_pages[pdf_index]:
                    label.setStyleSheet("border: 2px solid red;")
                else:
                    label.setStyleSheet("border: 2px solid black;")

    def normal_toggle_page(self, pdf_index, page_num):
        if page_num in self.selected_pages[pdf_index]:
            self.selected_pages[pdf_index].remove(page_num)
        else:
            self.selected_pages[pdf_index].add(page_num)
            self.last_selected_page[pdf_index] = page_num
        self.update_thumbnail_borders(pdf_index)

    def ctrl_toggle_page(self, pdf_index, page_num):
        if page_num in self.selected_pages[pdf_index]:
            self.selected_pages[pdf_index].remove(page_num)
        else:
            self.selected_pages[pdf_index].add(page_num)
            self.last_selected_page[pdf_index] = page_num
        self.update_thumbnail_borders(pdf_index)

    def shift_toggle_page(self, pdf_index, page_num):
        if self.last_selected_page[pdf_index] is not None:
            start_page = min(self.last_selected_page[pdf_index], page_num)
            end_page = max(self.last_selected_page[pdf_index], page_num)
            if page_num in self.selected_pages[pdf_index]:
                for p in range(start_page, end_page + 1):
                    self.selected_pages[pdf_index].discard(p)
            else:
                for p in range(start_page, end_page + 1):
                    self.selected_pages[pdf_index].add(p)
        else:
            if page_num in self.selected_pages[pdf_index]:
                self.selected_pages[pdf_index].remove(page_num)
            else:
                self.selected_pages[pdf_index].add(page_num)
        self.last_selected_page[pdf_index] = page_num
        self.update_thumbnail_borders(pdf_index)

    def generate_pdf(self):
        any_generated = False
        for pdf_index, pdf_doc in enumerate(self.pdf_docs):
            if pdf_doc and self.selected_pages[pdf_index]:
                new_pdf = fitz.open()
                for page_num in sorted(self.selected_pages[pdf_index]):
                    new_pdf.insert_pdf(pdf_doc, from_page=page_num, to_page=page_num)
                options = QtWidgets.QFileDialog.Options()
                suggested_filename = f"split_pdf_{pdf_index + 1}.pdf"
                save_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salvar PDF como",
                                                                     suggested_filename,
                                                                     "PDF Files (*.pdf)", options=options)
                if save_path:
                    try:
                        new_pdf.save(save_path)
                        any_generated = True
                    except Exception as e:
                        QtWidgets.QMessageBox.critical(self, "Erro", f"Erro ao salvar PDF: {e}")
                    finally:
                        new_pdf.close()
                else:
                    new_pdf.close()
        if any_generated:
            QtWidgets.QMessageBox.information(self, "Sucesso", "PDF(s) gerado(s) com sucesso!")
        else:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Nenhuma página selecionada ou operação cancelada.")

    def select_all_and_save(self):
        new_pdf = fitz.open()
        for pdf_doc in self.pdf_docs:
            if pdf_doc:
                new_pdf.insert_pdf(pdf_doc)
        options = QtWidgets.QFileDialog.Options()
        suggested_filename = "pdf_combinado.pdf"
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salvar PDF Combinado",
                                                             suggested_filename,
                                                             "PDF Files (*.pdf)", options=options)
        if save_path:
            try:
                new_pdf.save(save_path)
                QtWidgets.QMessageBox.information(self, "Sucesso", "PDF combinado gerado com sucesso!")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Erro", f"Erro ao salvar PDF: {e}")
            finally:
                new_pdf.close()
        else:
            new_pdf.close()

    def deselect_all_pages(self):
        for pdf_index, pdf_doc in enumerate(self.pdf_docs):
            if pdf_doc:
                self.selected_pages[pdf_index] = set()
                self.update_thumbnail_borders(pdf_index)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = PDFSplitterApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
