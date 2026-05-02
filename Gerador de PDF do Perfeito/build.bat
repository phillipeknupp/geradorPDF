@echo off
REM ============================================================
REM  Build script – Gerador de PDF do Perfeito
REM  Gera UM ÚNICO executável com imagens embutidas
REM  Uso: coloque este .bat na mesma pasta que pdf_manager.py,
REM       icon.png e splash.png, depois execute com duplo-clique.
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   Instalando / verificando PyInstaller...
echo ============================================================
pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERRO: nao foi possivel instalar o PyInstaller.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   Iniciando compilacao --onefile com imagens embutidas...
echo ============================================================

REM Separador de --add-data no Windows e ponto-e-virgula (;)
REM Formato:  origem;destino_dentro_do_exe
REM O destino "." significa: raiz do pacote (sys._MEIPASS)

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "GeradorPDF_Perfeito" ^
    --icon "icon.png" ^
    --add-data "icon.png;." ^
    --add-data "splash.png;." ^
    --hidden-import "fitz" ^
    --hidden-import "PyMuPDF" ^
    --hidden-import "PyQt5" ^
    --hidden-import "PyQt5.QtWidgets" ^
    --hidden-import "PyQt5.QtGui" ^
    --hidden-import "PyQt5.QtCore" ^
    --collect-all "fitz" ^
    --noconfirm ^
    pdf_manager.py

if errorlevel 1 (
    echo.
    echo ERRO na compilacao. Veja as mensagens acima.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   SUCESSO!
echo   Executavel gerado em:  dist\GeradorPDF_Perfeito.exe
echo ============================================================
pause
