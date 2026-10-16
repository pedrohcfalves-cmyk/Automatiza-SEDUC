"""
Configurações centrais do DARE. Ajuste aqui URLs, códigos fixos e pastas.

Na Central de Automações, este pacote fica em automacoes/dare/ (era dare_auto/ no
aplicativo DARE separado). Só duas coisas mudaram em relação ao original, as duas
marcadas com "Central" abaixo: onde ficam os dados e onde ficam o guia e a licença.
"""

import os
import sys
from pathlib import Path

# Pasta do pacote (automacoes/dare/, ao lado do terminal.py)
RAIZ = Path(__file__).resolve().parent

# ---- Aplicativo empacotado (executável gerado pelo PyInstaller) ---------------------------
# No executável, os arquivos do programa ficam numa pasta interna (somente leitura na prática).
# Os dados do usuário (PDFs, histórico, logs) vão para "Documentos\DARE Automação".
EMPACOTADO = bool(getattr(sys, "frozen", False))
# Recursos que acompanham o programa (guia de uso, licença). Central: ficam na pasta do
# pacote -- no executável, o instalador os copia para o mesmo caminho relativo.
RECURSOS = RAIZ


def _pasta_documentos() -> Path:
    """Pasta 'Documentos' do usuário (respeita redirecionamento para OneDrive no Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            guid = _GUID(0xFDD39AD0, 0x238F, 0x46AF,
                         (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            ponteiro = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(ponteiro)
            ) == 0:
                caminho = Path(ponteiro.value)
                ctypes.windll.ole32.CoTaskMemFree(ponteiro)
                return caminho
        except Exception:  # noqa: BLE001 - cai no padrão abaixo
            pass
    return Path.home() / "Documents"


# Onde ficam os dados do usuário. Pode ser trocado pela variável de ambiente DARE_PASTA_DADOS.
# Central: SEMPRE em Documentos\DARE Automação (a mesma pasta do aplicativo DARE instalado),
# rodando pelo código ou instalado -- nunca dentro da pasta do código. Assim o histórico,
# os pendentes e os PDFs do DARE instalado continuam aparecendo na Central.
if os.environ.get("DARE_PASTA_DADOS"):
    BASE_DADOS = Path(os.environ["DARE_PASTA_DADOS"])
else:
    BASE_DADOS = _pasta_documentos() / "DARE Automação"

# ---- Pastas e arquivos -------------------------------------------------------------------
# PDFs gerados. Para usar outra pasta, defina a variável de ambiente DARE_PASTA_PDF
# (ou escolha a pasta no aplicativo, em "Arquivos PDF").
PASTA_PDF_PADRAO = BASE_DADOS / "DARE_PDFs"
PASTA_PDF = Path(os.environ.get("DARE_PASTA_PDF") or PASTA_PDF_PADRAO)
PASTA_LOGS = BASE_DADOS / "logs"
PASTA_ERROS = PASTA_LOGS / "erros"  # capturas de tela quando algo falha
PASTA_DADOS = BASE_DADOS / "dados"
ARQ_LOG = PASTA_LOGS / "dare_automacao.log"
ARQ_ULTIMOS = PASTA_DADOS / "ultimos_dados.json"  # últimos dados digitados (viram padrão)
ARQ_HISTORICO = PASTA_DADOS / "historico.csv"  # um registro por execução
ARQ_LOTE = PASTA_DADOS / "lote_pendente.json"  # lançamentos em lote ainda não concluídos
ARQ_MAPEAMENTOS = PASTA_DADOS / "mapeamentos_planilha.json"  # colunas escolhidas por planilha/aba
ARQ_PREFERENCIAS = PASTA_DADOS / "preferencias.json"  # opções do aplicativo
ARQ_DESEMPENHO = PASTA_DADOS / "desempenho.csv"  # tempo de cada etapa de cada lançamento
ARQ_BENCHMARKS = PASTA_DADOS / "benchmarks.json"  # resultados dos testes de velocidade
PASTA_MODELOS = BASE_DADOS / "modelos"  # planilha modelo gerada pelo programa

# ---- Chrome em modo depuração -------------------------------------------------------------
PORTA_CDP = 9222
CDP_URL = f"http://127.0.0.1:{PORTA_CDP}"
# Perfil próprio do Chrome de depuração (o login nos sistemas fica salvo aqui).
PERFIL_CHROME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DARE_Chrome_Perfil"
# Perfil usado quando o Chrome não está instalado e o programa recorre ao Microsoft Edge.
PERFIL_EDGE = PERFIL_CHROME.parent / "DARE_Edge_Perfil"
# Para usar outro Chrome, defina a variável de ambiente DARE_CHROME_PATH com o caminho do chrome.exe.
ESPERA_CHROME = 30  # segundos esperando o Chrome abrir a porta de depuração

# ---- Sites --------------------------------------------------------------------------------
URL_DARE = "https://dare.sefin.ro.gov.br/avulso"
URL_SEI = "https://sei.sistemas.ro.gov.br/sip/login.php?sigla_orgao_sistema=RO&sigla_sistema=SEI"
HOST_DARE = "dare.sefin.ro.gov.br"
HOST_SEI = "sei.sistemas.ro.gov.br"

# ---- Valores fixos do DARE ----------------------------------------------------------------
ORGAO = "SEGEP - SUPERINTENDÊNCIA ESTADUAL DE GESTÃO DE PESSOAS"
CODIGO_RECEITA = "7155"
UNIDADE_GESTORA = "160001"
GESTAO = "00001"
VALOR_PADRAO = "100,00"

# ---- Valores fixos do SEI -----------------------------------------------------------------
SERIE_SEI = "310"  # tipo do documento externo
RADIO_NATO_DIGITAL = "optNato"  # id do rádio "Nato-digital"

# ---- Tempos (segundos) --------------------------------------------------------------------
TIMEOUT_ELEMENTO = 30
TIMEOUT_IMPRESSAO = 10
