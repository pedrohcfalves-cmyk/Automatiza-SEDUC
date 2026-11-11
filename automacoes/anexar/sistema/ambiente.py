"""
Ambiente do computador: onde está o Chrome, onde ficam os dados e o que
falta para o programa funcionar.

Só usa a biblioteca padrão do Python, de propósito: este módulo também é
usado pelo instalador (instalar.py), antes de qualquer pacote ser baixado.

Por que existe: o programa nasceu num computador só, com o Chrome em
C:\\Program Files\\... Em outro computador o Chrome pode estar em outra
pasta (instalação "só para mim" fica em AppData) e a pasta C:\\ pode não
aceitar gravação. Aqui ficam todas essas descobertas, num lugar só.

Ajustes avançados (variáveis de ambiente, normalmente não são necessários):
    ANEXAR_CHROME         caminho completo de um chrome.exe específico
    ANEXAR_PERFIL_CHROME  pasta do perfil do Chrome da automação

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""

import importlib.metadata
import os
import shutil
import sys
import tempfile

# A pasta do programa (onde ficam os .bat): duas acima deste arquivo (anexar/sistema/).
# Na Central: automacoes/anexar/sistema/ -> três acima é a pasta do programa.
PASTA_PROGRAMA = (os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False)
                  else os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Bibliotecas de que a automação precisa (nome no pip -> nome para mostrar).
BIBLIOTECAS = {
    "playwright": "Playwright (controla o Chrome)",
    "pymupdf": "PyMuPDF (lê os PDFs)",
    "pillow": "Pillow (imagens)",
    "pywebview": "pywebview (a janela da Central de Automações)",
}

PERFIL_PADRAO_WINDOWS = r"C:\ChromeAutomacao"
SITE_DO_CHROME = "https://www.google.com/chrome/"

_EXECUTAVEIS_NAO_WINDOWS = ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")


# ============================================================ Chrome


def _candidatos_chrome() -> list:
    """Lugares onde o Chrome costuma estar no Windows, do mais comum ao menos."""
    pastas = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),   # instalação "só para o meu usuário"
    ]
    lugares = [os.path.join(pasta, "Google", "Chrome", "Application", "chrome.exe") for pasta in pastas if pasta]
    lugares.append(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    lugares.append(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
    return lugares


def _chrome_pelo_registro() -> str:
    """O Windows guarda o caminho do Chrome no registro (qualquer pasta de instalação)."""
    if os.name != "nt":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    chave = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(raiz, chave) as aberta:
                valor, _tipo = winreg.QueryValueEx(aberta, "")
                if valor:
                    return valor
        except OSError:
            continue
    return ""


def achar_chrome() -> str:
    """Caminho do chrome.exe deste computador, ou None se não achar."""
    forcado = os.environ.get("ANEXAR_CHROME", "").strip().strip('"')
    if forcado and os.path.isfile(forcado):
        return forcado
    for caminho in _candidatos_chrome() + [_chrome_pelo_registro()]:
        if caminho and os.path.isfile(caminho):
            return caminho
    if os.name != "nt":
        for nome in _EXECUTAVEIS_NAO_WINDOWS:
            achado = shutil.which(nome)
            if achado:
                return achado
    return None


def pasta_perfil_chrome(criar: bool = True) -> str:
    """
    Pasta do perfil do Chrome da automação (guarda o login do SEI/SIGEF).

    Mantém C:\\ChromeAutomacao quando dá para usar (é onde os computadores
    que já usam o programa têm o login salvo). Se o computador não deixar
    gravar em C:\\, usa uma pasta do próprio usuário.
    """
    forcada = os.environ.get("ANEXAR_PERFIL_CHROME", "").strip().strip('"')
    if forcada:
        escolhida = forcada
    elif os.name == "nt":
        escolhida = PERFIL_PADRAO_WINDOWS
        if not os.path.isdir(escolhida) and criar:
            try:
                os.makedirs(escolhida, exist_ok=True)
            except OSError:
                escolhida = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                                         "AnexarDocumentos", "ChromeAutomacao")
    else:
        escolhida = os.path.join(os.path.expanduser("~"), ".anexar_documentos", "ChromeAutomacao")
    if criar:
        try:
            os.makedirs(escolhida, exist_ok=True)
        except OSError:
            pass
    return escolhida


# ============================================================ pastas e bibliotecas


def pasta_gravavel(pasta: str) -> bool:
    """True se dá para criar um arquivo nesta pasta (o programa guarda dados nela)."""
    try:
        with tempfile.TemporaryFile(dir=pasta):
            return True
    except OSError:
        return False


def versao_da_biblioteca(nome: str):
    if getattr(sys, "frozen", False):
        return "embutida"      # no .exe do instalador as bibliotecas vão dentro; não há metadados do pip
    try:
        return importlib.metadata.version(nome)
    except importlib.metadata.PackageNotFoundError:
        return None


# ============================================================ diagnóstico


def diagnostico() -> dict:
    """
    Tudo o que a tela mostra em "Este computador", mais a lista de problemas
    (cada um com um título curto e o que fazer, em linguagem simples).
    """
    chrome = achar_chrome()
    bibliotecas = {nome: versao_da_biblioteca(nome) for nome in BIBLIOTECAS}
    gravavel = pasta_gravavel(PASTA_PROGRAMA)
    problemas = []

    if not chrome:
        problemas.append({
            "id": "chrome",
            "titulo": "O Google Chrome não está instalado neste computador",
            "texto": "O programa usa o Chrome para entrar no SEI e no SIGEF. Instale o Google Chrome "
                     f"({SITE_DO_CHROME}), feche esta janela e abra o programa de novo.",
        })
    faltando = [BIBLIOTECAS[nome] for nome, versao in bibliotecas.items() if not versao]
    if faltando:
        problemas.append({
            "id": "bibliotecas",
            "titulo": "Faltam peças que o programa usa",
            "texto": "Faltam: " + "; ".join(faltando) + ". Feche esta janela e instale o programa de novo "
                     "com o instalador da Central de Automações.",
        })
    if not gravavel:
        problemas.append({
            "id": "pasta",
            "titulo": "O programa não consegue gravar nesta pasta",
            "texto": "Ele precisa guardar relatórios e o andamento dos processos. Copie a pasta inteira do programa "
                     "para um lugar seu (por exemplo, Documentos) e abra de lá. Se você abriu o arquivo .zip "
                     "sem extrair, extraia primeiro.",
        })

    return {
        "python": sys.version.split()[0],
        "congelado": bool(getattr(sys, "frozen", False)),
        "pasta_programa": PASTA_PROGRAMA,
        "pasta_gravavel": gravavel,
        "chrome": chrome,
        "perfil_chrome": pasta_perfil_chrome(criar=False),
        "bibliotecas": bibliotecas,
        "nomes_bibliotecas": BIBLIOTECAS,
        "sistema": sys.platform,
        "problemas": problemas,
        "site_chrome": SITE_DO_CHROME,
    }
