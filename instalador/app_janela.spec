# PyInstaller: empacota a janela (app_janela.py) com o Python e as
# bibliotecas dentro, numa pasta que roda sem nada instalado na máquina.
#
#     python -m PyInstaller instalador/app_janela.spec --noconfirm
#
# Sai em dist/Automacao SIGEF-SEI/. O Setup.exe (instalador.iss) é
# montado a partir dessa pasta. Passo a passo em instalador/CONSTRUIR.md.
import os

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
NOME = "Automacao SIGEF-SEI"

a = Analysis(
    [os.path.join(RAIZ, "app_janela.py")],
    pathex=[RAIZ],
    # A interface vai para janela/interface dentro do pacote, o mesmo
    # caminho relativo que o app_janela.py usa rodando pelo código.
    # O guia de uso e a licença do DARE vão para automacoes/dare, onde o
    # módulo DARE os procura (config.RECURSOS).
    datas=copy_metadata("pypdf") + [
        (os.path.join(RAIZ, "janela", "interface"), os.path.join("janela", "interface")),
        (os.path.join(RAIZ, "automacoes", "dare", "GUIA_DE_USO.html"), os.path.join("automacoes", "dare")),
        (os.path.join(RAIZ, "automacoes", "dare", "LICENCA.txt"), os.path.join("automacoes", "dare")),
        # Anexar Documentos: a licença (tela Ajuda e licença) e as estimativas de minutos à mão,
        # que são lidas e gravadas como arquivo (automacoes/anexar/aplicativo/metricas.py).
        (os.path.join(RAIZ, "automacoes", "anexar", "LICENSE"), os.path.join("automacoes", "anexar")),
        (os.path.join(RAIZ, "automacoes", "anexar", "aplicativo", "estimativas_manuais.py"),
         os.path.join("automacoes", "anexar", "aplicativo")),
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
    # psutil (CPU, memória, disco e rede). Os DAREs do mesmo processo são juntados
    # num PDF só pelo pypdf (puro Python), que o Diagnóstico lê pelos metadados.
    # O módulo Nota de Empenho (janela/modulo_ne.py + automacoes/ne) também só é
    # importado quando a pessoa abre a aba da NE.
    # Os módulos Cadastro de Credores (janela/modulo_cadastro.py + automacoes/cadastro) e
    # Anexar Documentos (janela/modulo_anexar.py + automacoes/anexar) também. O Anexar roda a
    # automação noutro processo (este mesmo .exe com --executor, ver app_janela.py), que abre o
    # fluxo pelo nome (importlib): por isso o pacote vai inteiro.
    hiddenimports=[
        "webview.platforms.edgechromium", "clr",
        "automacoes.bb.automacoes_bb", "janela.licenca",
        "janela.modulo_dare", "automacoes.dare.motor", "automacoes.dare.desempenho",
        "automacoes.dare.excel_com", "automacoes.dare.planilha_arquivo", "automacoes.dare.limpeza",
        "automacoes.dare.juntar", "pypdf",
        "janela.modulo_ne", "automacoes.ne.etapa", "automacoes.ne.lote", "automacoes.ne.metricas",
        "automacoes.ne.relatorio", "janela.modulo_geral", "automacoes.painel", "automacoes.relatorio_geral", "automacoes.geral",
        "janela.modulo_cadastro", "janela.modulo_anexar",
        *collect_submodules("automacoes.cadastro"), *collect_submodules("automacoes.anexar"),
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
