"""
Acesso ao Excel pelo pywin32 (COM). Só funciona no Windows, com o Excel instalado.

  • listar_abertas()      -> planilhas abertas agora no Excel (qualquer instância)
  • abrir_por_caminho()   -> usa a planilha se já estiver aberta; senão abre (somente leitura, invisível)
  • TabelaExcel           -> uma aba, com a mesma interface de planilha.TabelaMemoria
  • criar_modelo()        -> gera a planilha modelo (.xlsx)

O programa NUNCA grava na planilha do usuário: planilhas abertas por nós são lidas como
somente leitura e fechadas sem salvar.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import planilha, utils

log = logging.getLogger("dare.excel")

EXTENSOES = (".xlsx", ".xlsm", ".xlsb", ".xls")
XL_UP = -4162
XL_CELULAS_VISIVEIS = 12
XL_FORMATO_XLSX = 51
ERRO_EXCEL_MAX = -2146826000  # #N/A, #REF!, #DIV/0!... chegam como inteiros <= este valor

MODELO_CABECALHOS = [
    "Processo SEI",
    "CNPJ do órgão",
    "CPF do servidor",
    "CNPJ do recolhedor",
    "Mês/Ano referência",
    "Vencimento",
    "Valor (R$)",
]
MODELO_INSTRUCOES = [
    "MODELO DE PLANILHA - DARE avulso + anexo no SEI",
    "",
    "Uma linha = um DARE. Preencha a aba 'DARE' a partir da linha 2 (a linha 1 é o cabeçalho).",
    "",
    "Processo SEI ........ ex.: 0012.123456/2026-12",
    "CNPJ do órgão ....... 14 dígitos, com ou sem pontuação",
    "CPF do servidor ..... 11 dígitos, com ou sem pontuação",
    "CNPJ do recolhedor .. 14 dígitos, com ou sem pontuação",
    "Mês/Ano referência .. MMAAAA (ex.: 102026) ou 10/2026",
    "Vencimento .......... DD/MM/AAAA. Em branco = 1 mês à frente, em dia útil",
    "Valor (R$) .......... ex.: 7273,07. Em branco = 100,00",
    "",
    "A linha 2 é apenas um EXEMPLO: troque ou apague antes de rodar.",
    "Você pode usar sua própria planilha: o programa pergunta quais colunas usar.",
    "Dica: deixe as colunas de documentos como TEXTO para não perder zeros à esquerda.",
]


class ExcelIndisponivel(Exception):
    """pywin32/Excel não disponíveis (ou o arquivo não pôde ser aberto)."""


def _com():
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise ExcelIndisponivel(
            "A biblioteca pywin32 não está instalada (ou este não é o Windows). "
            "Instale com:  pip install pywin32"
        ) from exc
    pythoncom.CoInitialize()
    return pythoncom, win32com.client


# ---- Conversão das células vindas do COM --------------------------------------------------

def _celula(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v <= ERRO_EXCEL_MAX:
        return None  # célula com erro (#N/A...) é tratada como vazia
    if isinstance(v, datetime) or (hasattr(v, "year") and hasattr(v, "hour") and hasattr(v, "minute")):
        return datetime(v.year, v.month, v.day, v.hour, v.minute, getattr(v, "second", 0))
    if isinstance(v, date):
        return v
    return v


def _matriz(v: Any) -> list[list]:
    """Range.Value: valor solto (1 célula) ou tupla de tuplas -> lista de listas."""
    if not isinstance(v, tuple):
        return [[_celula(v)]]
    return [[_celula(c) for c in (linha if isinstance(linha, tuple) else (linha,))] for linha in v]


# ---- Pasta de trabalho aberta -------------------------------------------------------------

@dataclass
class PastaAberta:
    nome: str
    caminho: str
    objeto: Any = field(repr=False, default=None)
    aplicativo: Any = field(repr=False, default=None)
    aberta_por_nos: bool = False

    def abas(self) -> list[str]:
        return [ws.Name for ws in self.objeto.Worksheets]

    def tabela(self, aba: str) -> "TabelaExcel":
        return TabelaExcel(self.objeto, aba)

    def fechar(self) -> None:
        """Só fecha o que nós abrimos; planilhas do usuário ficam como estavam."""
        if not self.aberta_por_nos:
            return
        try:
            self.objeto.Close(False)
        except Exception:  # noqa: BLE001 - fechar é melhor-esforço
            log.debug("Falha ao fechar a planilha.", exc_info=True)
        try:
            if self.aplicativo is not None:
                self.aplicativo.Quit()
        except Exception:  # noqa: BLE001
            log.debug("Falha ao encerrar o Excel.", exc_info=True)


def _visivel(wb) -> bool:
    try:
        return wb.Windows.Count > 0  # PERSONAL.XLSB e afins ficam sem janela
    except Exception:  # noqa: BLE001
        return True


def _pastas_pela_rot(pythoncom, cliente) -> list:
    """Varre a Running Object Table: enxerga planilhas de TODAS as instâncias do Excel."""
    pastas = []
    rot = pythoncom.GetRunningObjectTable()
    contexto = pythoncom.CreateBindCtx(0)
    for moniker in rot.EnumRunning():
        try:
            nome = moniker.GetDisplayName(contexto, None)
        except Exception:  # noqa: BLE001 - entrada inválida na ROT
            continue
        if not str(nome).lower().endswith(EXTENSOES):
            continue
        try:
            dispatch = rot.GetObject(moniker).QueryInterface(pythoncom.IID_IDispatch)
            wb = cliente.Dispatch(dispatch)
            wb.Worksheets  # confirma que é uma pasta de trabalho do Excel
            pastas.append(wb)
        except Exception:  # noqa: BLE001
            log.debug("Ignorando '%s' na ROT.", nome, exc_info=True)
    return pastas


def _pastas_pela_aplicacao(cliente) -> list:
    try:
        app = cliente.GetActiveObject("Excel.Application")
        return [wb for wb in app.Workbooks]
    except Exception:  # noqa: BLE001 - Excel fechado
        return []


def listar_abertas() -> list[PastaAberta]:
    """Planilhas abertas no Excel agora. Lista vazia se o Excel não estiver aberto."""
    pythoncom, cliente = _com()
    candidatas = _pastas_pela_rot(pythoncom, cliente) or _pastas_pela_aplicacao(cliente)
    achadas: dict[str, PastaAberta] = {}
    for wb in candidatas:
        try:
            if not _visivel(wb):
                continue
            caminho = str(wb.FullName)
            achadas.setdefault(caminho.lower(), PastaAberta(str(wb.Name), caminho, wb))
        except Exception:  # noqa: BLE001
            continue
    log.info("Planilhas abertas encontradas: %d", len(achadas))
    return list(achadas.values())


def abrir_por_caminho(caminho: str | Path) -> PastaAberta:
    """Usa a planilha se já estiver aberta no Excel; senão abre em uma instância invisível."""
    arquivo = Path(str(caminho).strip().strip('"')).expanduser()
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
    if arquivo.suffix.lower() not in EXTENSOES:
        raise ExcelIndisponivel(f"Formato não suportado: {arquivo.suffix} (use .xlsx, .xlsm, .xlsb ou .xls).")
    alvo = str(arquivo.resolve()).lower()
    for pasta in listar_abertas():
        if pasta.caminho.lower() == alvo:
            return pasta
    _, cliente = _com()
    app = cliente.DispatchEx("Excel.Application")  # instância própria, sem mexer na do usuário
    try:
        app.Visible = False
        app.DisplayAlerts = False
        wb = app.Workbooks.Open(str(arquivo.resolve()), UpdateLinks=0, ReadOnly=True)
    except Exception as exc:  # noqa: BLE001
        try:
            app.Quit()
        except Exception:  # noqa: BLE001
            pass
        raise ExcelIndisponivel(
            f"Não consegui abrir '{arquivo.name}' (arquivo protegido por senha ou corrompido?): {exc}"
        ) from exc
    log.info("Planilha aberta (somente leitura): %s", arquivo)
    return PastaAberta(wb.Name, str(wb.FullName), wb, app, aberta_por_nos=True)


# ---- Uma aba ------------------------------------------------------------------------------

class TabelaExcel:
    """Uma aba do Excel, com a interface esperada por planilha.ler_lotes."""

    def __init__(self, pasta, aba: str):
        self.pasta = pasta
        try:
            self.ws = pasta.Worksheets(aba)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"A aba '{aba}' não existe nessa planilha.") from exc
        self.nome = str(pasta.Name)
        self.aba = str(self.ws.Name)

    def _intervalo(self, l1: int, c1: int, l2: int, c2: int):
        ws = self.ws
        return ws.Range(ws.Cells(l1, c1), ws.Cells(l2, c2))

    def ler(self, l1, c1, l2, c2) -> list[list]:
        """Valores como o Excel mostra (datas viram datetime)."""
        return _matriz(self._intervalo(l1, c1, l2, c2).Value)

    def ler_numeros(self, l1, c1, l2, c2) -> list[list]:
        """Valores brutos (Value2): números sem formatação de moeda, datas como número serial."""
        return _matriz(self._intervalo(l1, c1, l2, c2).Value2)

    def ultima_linha(self, colunas: list[int]) -> int:
        """Última linha preenchida em qualquer uma das colunas dadas (0 = nenhuma)."""
        ws, total, ultima = self.ws, self.ws.Rows.Count, 0
        for c in colunas:
            linha = total if not planilha.celula_vazia(ws.Cells(total, c).Value) else ws.Cells(total, c).End(XL_UP).Row
            if not planilha.celula_vazia(ws.Cells(linha, c).Value):
                ultima = max(ultima, int(linha))
        return ultima

    def linhas_ocultas(self, l1: int, l2: int) -> set[int]:
        """Linhas escondidas (filtro/ocultar) dentro do intervalo."""
        ws = self.ws
        try:
            visiveis: set[int] = set()
            areas = ws.Range(ws.Rows(l1), ws.Rows(l2)).SpecialCells(XL_CELULAS_VISIVEIS).Areas
            for area in areas:
                inicio = int(area.Row)
                visiveis.update(range(inicio, inicio + int(area.Rows.Count)))
            return set(range(l1, l2 + 1)) - visiveis
        except Exception:  # noqa: BLE001 - sem visíveis, ou erro: confere linha a linha
            return {n for n in range(l1, l2 + 1) if ws.Rows(n).Hidden}


# ---- Planilha modelo ----------------------------------------------------------------------

def criar_modelo(caminho: str | Path) -> Path:
    """Cria a planilha modelo (.xlsx) e devolve o caminho."""
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    _, cliente = _com()
    app = cliente.DispatchEx("Excel.Application")
    try:
        app.Visible = False
        app.DisplayAlerts = False
        wb = app.Workbooks.Add()
        ws = wb.Worksheets(1)
        ws.Name = "DARE"
        ultima_formatada = 1000
        formatos = ["@", "@", "@", "@", "@", "dd/mm/yyyy", "#,##0.00"]
        for col, (titulo, formato) in enumerate(zip(MODELO_CABECALHOS, formatos), 1):
            ws.Range(ws.Cells(2, col), ws.Cells(ultima_formatada, col)).NumberFormat = formato
            ws.Cells(1, col).Value = titulo
        exemplo = ["0012.123456/2026-12", "11222333000181", "52998224725", "11222333000181",
                   "102026", datetime.combine(utils.vencimento_padrao(), datetime.min.time()), 100.0]
        for col, valor in enumerate(exemplo, 1):
            ws.Cells(2, col).Value = valor
        cabecalho = ws.Range(ws.Cells(1, 1), ws.Cells(1, len(MODELO_CABECALHOS)))
        cabecalho.Font.Bold = True
        cabecalho.Interior.Color = 0xE6D8C4  # azul claro (BGR)
        ws.Columns("A:G").ColumnWidth = 22
        ajuda = wb.Worksheets.Add(After=ws)
        ajuda.Name = "Instruções"
        for i, linha in enumerate(MODELO_INSTRUCOES, 1):
            ajuda.Cells(i, 1).Value = linha
        ajuda.Cells(1, 1).Font.Bold = True
        ajuda.Columns("A:A").ColumnWidth = 90
        ws.Activate()
        wb.SaveAs(str(destino.resolve()), FileFormat=XL_FORMATO_XLSX)
        wb.Close(False)
    except Exception as exc:  # noqa: BLE001
        raise ExcelIndisponivel(f"Não consegui criar o modelo: {exc}") from exc
    finally:
        try:
            app.Quit()
        except Exception:  # noqa: BLE001
            pass
    log.info("Planilha modelo criada em %s", destino)
    return destino
