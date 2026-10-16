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
    # A interface vai para janela/interface dentro do pacote, o mesmo
    # caminho relativo que o app_janela.py usa rodando pelo código.
    # O guia de uso e a licença do DARE vão para automacoes/dare, onde o
    # módulo DARE os procura (config.RECURSOS).
    datas=[
        (os.path.join(RAIZ, "janela", "interface"), os.path.join("janela", "interface")),
        (os.path.join(RAIZ, "automacoes", "dare", "GUIA_DE_USO.html"), os.path.join("automacoes", "dare")),
        (os.path.join(RAIZ, "automacoes", "dare", "LICENCA.txt"), os.path.join("automacoes", "dare")),
    ],
    # O Playwright entra pelo hook do pyinstaller-hooks-contrib, que leva o
    # driver (node) junto. Navegador próprio não precisa: a automação usa
    # o Chrome da máquina.
    # O módulo do BB (automacoes/bb) é importado só quando a pessoa abre o
    # módulo, então vai listado aqui, com o que ele usa: Excel via COM
    # (pywin32), teclado/área de transferência (pyautogui, pyperclip -- o
    # pyautogui precisa do tkinter), CDP cru (websocket) e leitura de
    # .xlsx (openpyxl).
    # O módulo DARE (janela/modulo_dare.py + automacoes/dare) também só é
    # importado quando a pessoa abre o DARE; a aba Desempenho dele usa o
    # psutil (CPU, memória, disco e rede).
    hiddenimports=[
        "webview.platforms.edgechromium", "clr",
        "automacoes.bb.automacoes_bb", "janela.licenca",
        "janela.modulo_dare", "automacoes.dare.motor", "automacoes.dare.desempenho",
        "automacoes.dare.excel_com", "automacoes.dare.planilha_arquivo", "automacoes.dare.limpeza",
        "win32com.client", "pythoncom", "pywintypes", "win32gui", "win32con", "win32api",
        "pyautogui", "pyperclip", "websocket", "openpyxl", "psutil",
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
