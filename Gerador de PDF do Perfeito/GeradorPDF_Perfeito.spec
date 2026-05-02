# ============================================================
#  GeradorPDF_Perfeito.spec
#
#  Arquivo de especificação PyInstaller – build avançado.
#  Uso:
#      pyinstaller GeradorPDF_Perfeito.spec
#
#  Vantagens sobre o build.bat:
#   • Controle fino de cada etapa
#   • Melhor para CI/CD e builds repetíveis
#   • Permite ajustes sem redigitar toda a linha de comando
# ============================================================

import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ------------------------------------------------------------------
# Coleta TODOS os dados/binários do PyMuPDF (fitz)
# Necessário pois fitz embute DLLs e dados de fontes internamente
# ------------------------------------------------------------------
fitz_datas, fitz_binaries, fitz_hiddenimports = collect_all('fitz')

# ------------------------------------------------------------------
# Arquivos de imagem a embutir no executável
# Formato: (caminho_origem, pasta_destino_dentro_do_exe)
# '.' = raiz de sys._MEIPASS (onde resource_path() vai buscar)
# ------------------------------------------------------------------
added_files = [
    ('icon.png',   '.'),
    ('splash.png', '.'),
]

# ------------------------------------------------------------------
# Análise do script principal
# ------------------------------------------------------------------
a = Analysis(
    ['pdf_manager.py'],
    pathex=['.'],
    binaries=fitz_binaries,
    datas=fitz_datas + added_files,
    hiddenimports=fitz_hiddenimports + [
        'PyQt5',
        'PyQt5.QtWidgets',
        'PyQt5.QtGui',
        'PyQt5.QtCore',
        'PyQt5.QtPrintSupport',
        'fitz',
        'collections',
        'subprocess',
        'importlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclui módulos pesados não utilizados para reduzir tamanho
        'matplotlib',
        'scipy',
        'pandas',
        'PIL',            # Pillow (não usamos diretamente)
        'tkinter',
        'wx',
        'gi',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ------------------------------------------------------------------
# Empacota tudo num único arquivo .pkg
# ------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ------------------------------------------------------------------
# Gera o executável final --onefile
# ------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GeradorPDF_Perfeito',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # Comprime com UPX se disponível (reduz tamanho)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # Sem janela de console (modo GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.png',    # Ícone do executável no Windows
)
