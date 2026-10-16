"""
Leitura de planilhas, independente do layout: mapeamento de colunas, normalização dos valores
das células (texto, número, data) e conversão de cada linha em um lançamento (DadosDare).

Esta parte não depende do Excel: lê através de uma "tabela" (objeto com ler/ler_numeros/
ultima_linha/linhas_ocultas). O acesso real ao Excel fica em excel_com.py.
"""

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import config, utils
from .modelos import DadosDare

log = logging.getLogger("dare.planilha")

# ---- Campos -------------------------------------------------------------------------------

CAMPOS = ["processo", "cnpj", "cpf", "cnpj_recolhedor", "mes_ano_referencia", "vencimento", "valor"]
ROTULOS = {
    "processo": "Processo SEI",
    "cnpj": "CNPJ (órgão)",
    "cpf": "CPF do servidor",
    "cnpj_recolhedor": "CNPJ do recolhedor",
    "mes_ano_referencia": "Mês/ano de referência",
    "vencimento": "Data de vencimento",
    "valor": "Valor",
}
# Vencimento e valor têm padrão (1 mês à frente / 100,00); os demais precisam de uma origem.
OBRIGATORIOS = ["processo", "cnpj", "cpf", "cnpj_recolhedor", "mes_ano_referencia"]
PADRAO_DESCRICAO = {
    "vencimento": "padrão: 1 mês à frente, em dia útil",
    "valor": f"padrão: {config.VALOR_PADRAO}",
}

MAX_COLUNAS_CABECALHO = 60
MAX_LINHAS_CABECALHO = 30
EXCEL_EPOCA = date(1899, 12, 30)


# ---- Colunas (A, B, ..., AA) --------------------------------------------------------------

def letra_para_numero(letras: str) -> int:
    n = 0
    for ch in letras.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def numero_para_letra(n: int) -> str:
    letras = ""
    while n > 0:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


# ---- Origem de cada campo e mapeamento ---------------------------------------------------

@dataclass(frozen=True)
class Origem:
    """De onde vem um campo: uma coluna da planilha OU um valor fixo para todas as linhas."""

    coluna: int | None = None
    fixo: str | None = None

    @property
    def vazia(self) -> bool:
        return self.coluna is None and self.fixo is None

    def para_dict(self) -> dict:
        return {"coluna": self.coluna, "fixo": self.fixo}

    @classmethod
    def de_dict(cls, d: dict) -> "Origem":
        coluna, fixo = d.get("coluna"), d.get("fixo")
        return cls(int(coluna) if coluna else None, None if fixo is None else str(fixo))


@dataclass
class Mapeamento:
    campos: dict[str, Origem] = field(default_factory=dict)
    linha_cabecalho: int = 0  # 0 = a planilha não tem cabeçalho

    def origem(self, campo: str) -> Origem:
        return self.campos.get(campo, Origem())

    def faltando(self) -> list[str]:
        return [c for c in OBRIGATORIOS if self.origem(c).vazia]

    def colunas_usadas(self) -> list[int]:
        return sorted({o.coluna for o in self.campos.values() if o.coluna})

    def para_dict(self) -> dict:
        return {
            "linha_cabecalho": self.linha_cabecalho,
            "campos": {c: o.para_dict() for c, o in self.campos.items() if not o.vazia},
        }

    @classmethod
    def de_dict(cls, d: dict) -> "Mapeamento":
        campos = {c: Origem.de_dict(o) for c, o in (d.get("campos") or {}).items() if c in CAMPOS}
        return cls(campos, int(d.get("linha_cabecalho") or 0))


# ---- Reconhecimento automático de cabeçalhos ----------------------------------------------

_PALAVRAS_VAZIAS = {"de", "do", "da", "dos", "das", "o", "a", "e"}


def normalizar(texto: Any) -> str:
    """Minúsculas, sem acento nem pontuação, sem 'de/do/da': 'Nº do Processo' -> 'no processo'."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(p for p in t.split() if p not in _PALAVRAS_VAZIAS)


_SINONIMOS = {
    "processo": ["processo", "processo sei", "numero processo", "no processo", "n processo",
                 "num processo", "sei", "protocolo"],
    "cnpj": ["cnpj", "cnpj orgao", "cnpj contribuinte", "cnpj unidade", "cnpj empresa"],
    "cpf": ["cpf", "cpf servidor", "cpf contribuinte", "cpf funcionario"],
    "cnpj_recolhedor": ["cnpj recolhedor", "recolhedor", "cnpj recolhimento"],
    "mes_ano_referencia": ["referencia", "mes ano", "mes ano referencia", "mes referencia",
                           "competencia", "ref", "periodo"],
    "vencimento": ["vencimento", "data vencimento", "venc", "dt vencimento", "data venc",
                   "dt venc"],
    "valor": ["valor", "valor principal", "valor dare", "valor total", "valor pagar", "valor r"],
}
SINONIMOS = {c: [normalizar(s) for s in lista] for c, lista in _SINONIMOS.items()}


def _pontuar(cabecalho_norm: str, campo: str) -> int:
    tokens = cabecalho_norm.split()
    if not tokens:
        return 0
    tem_recolh = any(t.startswith("recolh") for t in tokens)
    if campo == "cnpj" and tem_recolh:
        return 0
    if campo == "cnpj_recolhedor" and not tem_recolh:
        return 0
    melhor = 0
    for sin in SINONIMOS[campo]:
        if cabecalho_norm == sin:
            return 100
        palavras = sin.split()
        if all(p in tokens for p in palavras):
            melhor = max(melhor, 85 - 3 * (len(tokens) - len(palavras)))
    return melhor


def sugerir_mapeamento(cabecalhos: dict[int, Any]) -> dict[str, Origem]:
    """A partir de {coluna: texto do cabeçalho}, sugere qual coluna alimenta cada campo."""
    normalizados = {col: normalizar(txt) for col, txt in cabecalhos.items()}
    pares = []
    for campo in CAMPOS:
        for col, norm in normalizados.items():
            pontos = _pontuar(norm, campo)
            if pontos >= 60:
                pares.append((pontos, campo, col))
    pares.sort(key=lambda p: (-p[0], p[2]))
    usados_campos: set[str] = set()
    usadas_colunas: set[int] = set()
    sugestao: dict[str, Origem] = {}
    for _, campo, col in pares:
        if campo in usados_campos or col in usadas_colunas:
            continue
        sugestao[campo] = Origem(coluna=col)
        usados_campos.add(campo)
        usadas_colunas.add(col)
    return sugestao


def ler_cabecalhos(tabela, linha: int) -> dict[int, str]:
    """{coluna: texto} da linha de cabeçalho (só as células preenchidas)."""
    if linha < 1:
        return {}
    valores = tabela.ler(linha, 1, linha, MAX_COLUNAS_CABECALHO)[0]
    return {i + 1: texto_celula(v) for i, v in enumerate(valores) if not _vazio(v)}


def detectar_linha_cabecalho(tabela) -> int:
    """Procura nas primeiras linhas a que mais parece um cabeçalho (>= 2 campos reconhecidos)."""
    bloco = tabela.ler(1, 1, MAX_LINHAS_CABECALHO, MAX_COLUNAS_CABECALHO)
    melhor_linha, melhor_pontos = 0, 1
    for n, linha in enumerate(bloco, 1):
        cabecalhos = {i + 1: texto_celula(v) for i, v in enumerate(linha) if isinstance(v, str)}
        reconhecidos = len(sugerir_mapeamento(cabecalhos))
        if reconhecidos > melhor_pontos:
            melhor_linha, melhor_pontos = n, reconhecidos
    return melhor_linha


def interpretar_origem(texto: str, cabecalhos: dict[int, str]) -> Origem:
    """
    O que o usuário digitou para um campo:  C | AB | 3 (coluna)  ·  nome do cabeçalho  ·
    =valor fixo  ·  - (nenhuma). Levanta ValueError se não entender.
    """
    t = texto.strip()
    if t in ("", "-"):
        return Origem()
    if t.startswith("="):
        fixo = t[1:].strip()
        if not fixo:
            raise ValueError("Depois do '=' informe o valor fixo (ex.: =100,00).")
        return Origem(fixo=fixo)
    if re.fullmatch(r"[A-Za-z]{1,3}", t):
        return Origem(coluna=letra_para_numero(t))
    if t.isdigit() and int(t) >= 1:
        return Origem(coluna=int(t))
    alvo = normalizar(t)
    exatas = [c for c, h in cabecalhos.items() if normalizar(h) == alvo]
    parciais = [c for c, h in cabecalhos.items() if alvo and alvo in normalizar(h)]
    for candidatas in (exatas, parciais):
        if len(candidatas) == 1:
            return Origem(coluna=candidatas[0])
        if len(candidatas) > 1:
            letras = ", ".join(numero_para_letra(c) for c in candidatas)
            raise ValueError(f"'{t}' aparece em mais de uma coluna ({letras}). Use a letra.")
    raise ValueError(f"Não achei a coluna '{t}'. Use a letra (ex.: C), o nome do cabeçalho ou =valor.")


# ---- Conversão dos valores das células ----------------------------------------------------

def _vazio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


celula_vazia = _vazio  # nome público, usado pelo excel_com


def texto_celula(v: Any) -> str:
    """Texto "humano" de uma célula: 61463035268.0 -> '61463035268'; data -> 'dd/mm/aaaa'."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, (int, Decimal)) and not isinstance(v, bool):
        return str(int(v)) if v == int(v) else format(v, "f")
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else format(v, ".10g")
    return str(v).strip()


def para_documento(v: Any, digitos: int, nome: str, validador) -> str:
    """CPF/CNPJ -> só dígitos. Recupera os zeros à esquerda que o Excel costuma comer."""
    t = texto_celula(v)
    d = utils.somente_digitos(t)
    if not d:
        raise ValueError(f"{nome} vazio")
    if len(d) < digitos:
        d = d.zfill(digitos)
    if len(d) != digitos:
        raise ValueError(f"{nome} deve ter {digitos} dígitos (veio '{t}')")
    if not validador(d):
        raise ValueError(f"{nome} inválido ('{t}')")
    return d


def para_processo(v: Any) -> str:
    t = texto_celula(v)
    try:
        return utils.validar_processo(t)
    except ValueError:
        raise ValueError(f"processo inválido ('{t}')")


def para_mes_ano(v: Any) -> str:
    """-> 'MMAAAA'. Aceita data, 102026, 92026, '10/2026', '2026-10', '10/26' e 'out/2026'."""
    if isinstance(v, (datetime, date)):
        return f"{v.month:02d}{v.year}"
    t = texto_celula(v)
    if not t:
        raise ValueError("mês/ano de referência vazio")
    m = re.fullmatch(r"(\d{4})\s*[-/.]\s*(\d{1,2})", t)  # 2026-10
    if m:
        return utils.validar_mes_ano(f"{int(m.group(2)):02d}{m.group(1)}")
    m = re.fullmatch(r"([a-zA-Zçç]{3,10})\s*[-/. ]\s*(\d{2}|\d{4})", normalizar(t) or t)
    if m:
        mes = next((i + 1 for i, abrev in enumerate(utils.MESES) if m.group(1).startswith(abrev)), 0)
        ano = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
        if mes:
            return utils.validar_mes_ano(f"{mes:02d}{ano}")
    d = utils.somente_digitos(t)
    if len(d) == 4:  # MMAA
        d = d[:2] + "20" + d[2:]
    elif len(d) == 5:  # M AAAA (o Excel comeu o zero)
        d = "0" + d
    try:
        return utils.validar_mes_ano(d)
    except ValueError:
        raise ValueError(f"mês/ano inválido ('{t}'); use MMAAAA")


_FORMATOS_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")


def para_data(v: Any) -> date | None:
    """Data da célula (data de verdade, número serial do Excel ou texto). Vazio -> None."""
    if _vazio(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        if 30000 <= float(v) <= 80000:  # 1982..2119 como número serial do Excel
            return EXCEL_EPOCA + timedelta(days=int(float(v)))
        raise ValueError(f"data inválida ('{texto_celula(v)}')")
    t = str(v).strip()
    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(t, formato).date()
        except ValueError:
            continue
    raise ValueError(f"data inválida ('{t}'); use DD/MM/AAAA")


def para_valor(v_natural: Any, v_numero: Any) -> str:
    """Valor em reais -> '7.273,07'. Vazio -> valor padrão. Prefere o número puro do Excel."""
    base = v_numero if not _vazio(v_numero) else v_natural
    if _vazio(base):
        return utils.formatar_valor(config.VALOR_PADRAO)
    if isinstance(base, (int, float, Decimal)) and not isinstance(base, bool):
        texto = f"{round(float(base), 2):.2f}".replace(".", ",")
    else:
        texto = str(base).strip()
    try:
        return utils.formatar_valor(texto)
    except ValueError:
        raise ValueError(f"valor inválido ('{texto_celula(base)}')")


# ---- Leitura linha a linha ----------------------------------------------------------------

@dataclass
class Problema:
    linha: int
    mensagem: str


@dataclass
class ResultadoLeitura:
    lotes: list[DadosDare] = field(default_factory=list)
    problemas: list[Problema] = field(default_factory=list)
    vazias: int = 0
    ocultas: int = 0
    lidas: int = 0  # linhas com algum dado (válidas + com problema)


def _celula(matriz: list[list], i: int, coluna: int | None) -> Any:
    if coluna is None or i >= len(matriz) or coluna - 1 >= len(matriz[i]):
        return None
    return matriz[i][coluna - 1]


def ler_lotes(tabela, mapeamento: Mapeamento, linha_inicial: int, linha_final: int) -> ResultadoLeitura:
    """
    Lê as linhas [linha_inicial, linha_final], uma a uma, e converte cada uma em DadosDare.
    Linhas totalmente vazias são puladas; linhas ocultas (filtro) também; linhas com dado
    inválido viram 'problemas' (com o número da linha) e ficam de fora.
    """
    if mapeamento.faltando():
        nomes = ", ".join(ROTULOS[c] for c in mapeamento.faltando())
        raise ValueError(f"Falta indicar de onde vêm: {nomes}.")
    if linha_inicial < 1 or linha_final < linha_inicial:
        raise ValueError("Intervalo de linhas inválido.")
    colunas = mapeamento.colunas_usadas()
    ultima = max(colunas) if colunas else 1
    natural = tabela.ler(linha_inicial, 1, linha_final, ultima)
    numeros = tabela.ler_numeros(linha_inicial, 1, linha_final, ultima)
    ocultas = tabela.linhas_ocultas(linha_inicial, linha_final)

    resultado = ResultadoLeitura()
    for i in range(linha_final - linha_inicial + 1):
        n = linha_inicial + i
        if n in ocultas:
            resultado.ocultas += 1
            continue

        def bruto(campo: str, matriz: list[list] = natural) -> Any:
            o = mapeamento.origem(campo)
            return o.fixo if o.fixo is not None else _celula(matriz, i, o.coluna)

        if all(_vazio(_celula(natural, i, c)) for c in colunas):
            resultado.vazias += 1
            continue
        resultado.lidas += 1

        erros: list[str] = []
        valores: dict[str, Any] = {}

        def tentar(campo: str, funcao) -> None:
            try:
                valores[campo] = funcao()
            except ValueError as exc:
                erros.append(f"{ROTULOS[campo]}: {exc}")

        tentar("processo", lambda: para_processo(bruto("processo")))
        tentar("cnpj", lambda: para_documento(bruto("cnpj"), 14, "CNPJ", utils.validar_cnpj))
        tentar("cpf", lambda: para_documento(bruto("cpf"), 11, "CPF", utils.validar_cpf))
        tentar("cnpj_recolhedor", lambda: para_documento(
            bruto("cnpj_recolhedor"), 14, "CNPJ do recolhedor", utils.validar_cnpj))
        tentar("mes_ano_referencia", lambda: para_mes_ano(bruto("mes_ano_referencia")))
        tentar("vencimento", lambda: para_data(bruto("vencimento")) or utils.vencimento_padrao())
        tentar("valor", lambda: para_valor(bruto("valor"), bruto("valor", numeros)))

        if erros:
            resultado.problemas.append(Problema(n, "; ".join(erros)))
            continue
        resultado.lotes.append(DadosDare(
            valores["processo"], valores["cnpj"], valores["cpf"], valores["cnpj_recolhedor"],
            valores["mes_ano_referencia"], valores["vencimento"], valores["valor"],
            origem=f"linha {n}",
        ))
    return resultado


def ultima_linha_com_dados(tabela, mapeamento: Mapeamento) -> int:
    """Última linha preenchida nas colunas mapeadas (0 se não houver)."""
    colunas = mapeamento.colunas_usadas()
    return tabela.ultima_linha(colunas) if colunas else 0


# ---- Mapeamentos salvos (por planilha + aba) ----------------------------------------------

def chave_mapeamento(nome_planilha: str, aba: str) -> str:
    return f"{nome_planilha.strip().lower()}|{aba.strip().lower()}"


def _carregar_todos() -> dict:
    try:
        bruto = json.loads(config.ARQ_MAPEAMENTOS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Não consegui ler %s (%s). Ignorando.", config.ARQ_MAPEAMENTOS, exc)
        return {}
    return bruto if isinstance(bruto, dict) else {}


def carregar_mapeamento(chave: str) -> Mapeamento | None:
    item = _carregar_todos().get(chave)
    if not isinstance(item, dict):
        return None
    try:
        mapeamento = Mapeamento.de_dict(item)
    except (TypeError, ValueError):
        return None
    return mapeamento if mapeamento.campos else None


def salvar_mapeamento(chave: str, mapeamento: Mapeamento) -> None:
    todos = _carregar_todos()
    todos[chave] = mapeamento.para_dict()
    config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = Path(f"{config.ARQ_MAPEAMENTOS}.tmp")
    temporario.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, config.ARQ_MAPEAMENTOS)


# ---- Tabela em memória (testes e uso sem Excel) -------------------------------------------

class TabelaMemoria:
    """Mesma interface da TabelaExcel, sobre uma lista de listas (linha 1 = índice 0)."""

    def __init__(self, dados: list[list], nome: str = "memoria.xlsx", aba: str = "Plan1",
                 ocultas: set[int] | None = None):
        self.dados, self.nome, self.aba = dados, nome, aba
        self._ocultas = set(ocultas or ())

    def _bloco(self, l1: int, c1: int, l2: int, c2: int, numeros: bool) -> list[list]:
        saida = []
        for n in range(l1, l2 + 1):
            linha = self.dados[n - 1] if n - 1 < len(self.dados) else []
            fila = []
            for c in range(c1, c2 + 1):
                v = linha[c - 1] if c - 1 < len(linha) else None
                if numeros and isinstance(v, datetime):
                    v = (v.date() - EXCEL_EPOCA).days
                elif numeros and isinstance(v, date):
                    v = (v - EXCEL_EPOCA).days
                fila.append(v)
            saida.append(fila)
        return saida

    def ler(self, l1, c1, l2, c2):
        return self._bloco(l1, c1, l2, c2, numeros=False)

    def ler_numeros(self, l1, c1, l2, c2):
        return self._bloco(l1, c1, l2, c2, numeros=True)

    def ultima_linha(self, colunas: list[int]) -> int:
        ultima = 0
        for n, linha in enumerate(self.dados, 1):
            if any(c - 1 < len(linha) and not _vazio(linha[c - 1]) for c in colunas):
                ultima = n
        return ultima

    def linhas_ocultas(self, l1: int, l2: int) -> set[int]:
        return {n for n in self._ocultas if l1 <= n <= l2}
