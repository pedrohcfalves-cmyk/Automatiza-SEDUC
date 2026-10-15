# PyInstaller: empacota a janela (app_janela.py) com o Python e as
# bibliotecas dentro, numa pasta que roda sem nada instalado na máquina.
#
#     python -m PyInstaller instalador/app_janela.spec --noconfirm
#
# Sai em dist/Automacao SIGEF-SEI/. O Setup.exe (instalador.iss) é
# montado a partir dessa pasta. Passo a passo em instalador/CONSTRUIR.md.
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
NOME = "Automacao SIGEF-SEI"

a = Analysis(
    [os.path.join(RAIZ, "app_janela.py")],
    pathex=[RAIZ],
    datas=[(os.path.join(RAIZ, "interface"), "interface")],
    # O Playwright entra pelo hook do pyinstaller-hooks-contrib, que leva o
    # driver (node) junto. Navegador próprio não precisa: a automação usa
    # o Chrome da máquina.
    # Os módulos do Amigo e do BB (modulos/) são importados só quando a
    # pessoa abre o módulo, então vão listados aqui, com o que eles usam:
    # Excel via COM (pywin32), teclado/área de transferência (pyautogui,
    # pyperclip -- o pyautogui precisa do tkinter), CDP cru (websocket) e
    # leitura de .xlsx (openpyxl).
    hiddenimports=[
        "webview.platforms.edgechromium", "clr",
        "modulos.amigo", "modulos.automacoes_bb",
        "win32com.client", "pythoncom", "pywintypes", "win32gui", "win32con", "win32api",
        "pyautogui", "pyperclip", "websocket", "openpyxl",
    ],
    excludes=["unittest", "pydoc", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOME,
    icon=os.path.join(RAIZ, "lancador", "icone.ico"),
    version=os.path.join(SPECPATH, "versao_exe.txt"),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=NOME, upx=False)
