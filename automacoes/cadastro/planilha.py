"""Leitura e gravação da planilha do Excel via COM (pywin32)."""

import os
import time
from typing import NamedTuple

from .bancos import normalizar
from .config import (
    COLUNAS_BUSCA_CABECALHO,
    COLUNAS_PADRAO,
    LINHAS_BUSCA_CABECALHO,
    XL_UP,
)
from .modelos import Lote, limpar

# Cabeçalhos aceitos na detecção automática das colunas (normalizados)
CABECALHOS = {
    "nome": ("SERVIDOR", "NOMEDOSERVIDOR", "NOMEDOCREDOR", "CREDOR", "FAVORECIDO",
             "BENEFICIARIO", "NOME"),
    "cpf": ("CPF", "NUCPF", "CPFCNPJ"),
    "banco": ("BANCO", "CODIGODOBANCO", "CODBANCO", "CDBANCO"),
    "agencia": ("AGENCIA", "AGBANCARIA", "AG"),
    "conta": ("CC", "CONTA", "CONTACORRENTE", "NUCONTA", "CONTABANCARIA"),
}

# Cabeçalhos que nunca são o nome do credor
CABECALHOS_IGNORADOS = ("ESCOLA", "MUNICIPIO", "EMPRESA", "ORGAO", "UNIDADE")


class ErroPlanilha(Exception):
    """Excel indisponível ou pasta de trabalho inacessível."""


class Gravacao(NamedTuple):
    endereco: str
    avisos: list


# ------------------------------------------------------------- utilidades

def letra_para_indice(letra: str) -> int:
    indice = 0

    for caractere in letra.strip().upper():
        if not caractere.isalpha():
            break

        indice = indice * 26 + (ord(caractere) - 64)

    return indice


def indice_para_letra(indice: int) -> str:
    letra = ""

    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letra = chr(65 + resto) + letra

    return letra


def texto_celula(valor) -> str:
    if valor is None:
        return ""

    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))

    return str(valor).strip()


def endereco(celula) -> str:
    """Address é propriedade no late binding e método no early binding."""
    valor = celula.Address

    if not isinstance(valor, str):
        valor = valor(False, False)

    return valor.replace("$", "")


def _matriz(valor) -> list:
    """Range.Value devolve escalar (1 célula) ou tupla de tuplas: sempre matriz."""
    if isinstance(valor, tuple):
        return [list(linha) for linha in valor]

    return [[valor]]


# ------------------------------------------------------- Excel e arquivos

def conectar_excel():
    """Usa o Excel já aberto ou abre um novo, visível."""
    try:
        import win32com.client as win32
    except ImportError as erro:
        raise ErroPlanilha("Biblioteca pywin32 não encontrada. Instale com: pip install pywin32") from erro

    try:
        return win32.GetActiveObject("Excel.Application")
    except Exception:
        pass

    try:
        excel = win32.Dispatch("Excel.Application")
        excel.Visible = True
        return excel
    except Exception as erro:
        raise ErroPlanilha("Não foi possível abrir o Microsoft Excel neste computador.") from erro


def pastas_abertas(excel) -> list:
    return [pasta.Name for pasta in excel.Workbooks]


def abrir_arquivo(excel, caminho: str) -> tuple:
    """Abre o arquivo, reaproveitando a pasta se já estiver aberta: (pasta, já_aberta)."""
    caminho = caminho.strip().strip('"').strip("'")
    nome = os.path.basename(caminho).lower()

    for pasta in excel.Workbooks:
        if pasta.Name.lower() == nome or pasta.FullName.lower() == caminho.lower():
            return pasta, True

    # Workbooks.Open pode devolver None: nesse caso a pasta ativa é a recém-aberta
    pasta = excel.Workbooks.Open(caminho) or excel.ActiveWorkbook

    if pasta is None:
        raise ErroPlanilha("Não foi possível obter a pasta de trabalho.")

    return pasta, False


def abas_da_pasta(pasta) -> list:
    return [aba.Name for aba in pasta.Worksheets]


# ------------------------------------------------------------- planilha

class Planilha:
    """Uma aba de uma pasta de trabalho aberta no Excel."""

    def __init__(self, pasta, aba):
        self.pasta = pasta
        self.aba = aba

    @classmethod
    def da_pasta(cls, pasta, nome_aba: str) -> "Planilha":
        return cls(pasta, pasta.Worksheets(nome_aba))

    @property
    def caminho(self) -> str:
        return self.pasta.FullName

    @property
    def nome_aba(self) -> str:
        return self.aba.Name

    @property
    def somente_leitura(self) -> bool:
        return bool(self.pasta.ReadOnly)

    def _faixa(self, linha1: int, coluna1: int, linha2: int, coluna2: int) -> list:
        """Lê um bloco inteiro numa única chamada COM (bem mais rápido que célula a célula)."""
        celulas = self.aba.Range(self.aba.Cells(linha1, coluna1), self.aba.Cells(linha2, coluna2))
        return _matriz(celulas.Value)

    def texto(self, linha: int, coluna: int) -> str:
        return texto_celula(self.aba.Cells(linha, coluna).Value)

    # ------------------------------------------------------ mapa das colunas

    def detectar_colunas(self) -> tuple:
        """Procura a linha de cabeçalho; devolve ({campo: índice}, 1ª linha de dados)."""
        bloco = self._faixa(1, 1, LINHAS_BUSCA_CABECALHO, COLUNAS_BUSCA_CABECALHO)

        for linha, valores in enumerate(bloco, 1):
            titulos = {coluna: normalizar(texto_celula(valor))
                       for coluna, valor in enumerate(valores, 1)}

            if "CPF" not in titulos.values():
                continue

            colunas = _casar_cabecalhos(titulos)

            if len(colunas) == len(CABECALHOS):
                return colunas, linha + 1

        return {}, 0

    def colunas_sugeridas(self) -> tuple:
        """Colunas detectadas pelo cabeçalho ou, na falta dele, as padrão.

        Devolve (colunas, primeira linha de dados, detectou?).
        """
        colunas, primeira = self.detectar_colunas()

        if colunas:
            return colunas, primeira, True

        padrao = {campo: letra_para_indice(letra) for campo, letra in COLUNAS_PADRAO.items()}
        return padrao, 2, False

    def amostra(self, colunas: dict, primeira: int) -> list:
        """[(campo, letra, título, exemplo)] para conferência do mapa das colunas."""
        return [
            (campo, indice_para_letra(coluna),
             self.texto(max(primeira - 1, 1), coluna), self.texto(primeira, coluna))
            for campo, coluna in colunas.items()
        ]

    # ------------------------------------------------------ leitura/gravação

    def ler_lote(self, linha: int, colunas: dict) -> tuple:
        """Lê a linha numa só chamada: devolve (Lote, texto bruto do banco)."""
        inicio, fim = min(colunas.values()), max(colunas.values())
        valores = self._faixa(linha, inicio, linha, fim)[0]
        bruto = {campo: texto_celula(valores[coluna - inicio]) for campo, coluna in colunas.items()}

        lote = Lote(**{campo: limpar(campo, valor) for campo, valor in bruto.items()})
        return lote, bruto["banco"]

    def ultima_linha(self, colunas: dict) -> int:
        return int(self.aba.Cells(self.aba.Rows.Count, colunas["cpf"]).End(XL_UP).Row)

    def gravar(self, linha: int, texto: str, coluna: str) -> Gravacao:
        """Escreve o diagnóstico da linha e salva a pasta; devolve endereço e avisos."""
        celula = f"{coluna}{linha}"
        avisos = []

        # Excel recusa chamadas COM enquanto uma célula está em edição: tenta de novo
        for tentativa in (1, 2, 3):
            try:
                alvo = self.aba.Range(celula)

                # Em célula mesclada só a primeira do bloco aceita valor
                if alvo.MergeCells:
                    alvo = alvo.MergeArea.Cells(1, 1)

                alvo.Value = texto
                celula = endereco(alvo)

                if not texto_celula(alvo.Value):
                    avisos.append(f"ATENÇÃO: a célula {celula} continua vazia após a gravação.")
                elif alvo.EntireColumn.Hidden:
                    avisos.append("ATENÇÃO: a coluna do resultado está oculta no Excel "
                                  "(botão direito > Reexibir).")
                break

            except Exception as erro:
                if tentativa == 3:
                    avisos.append(f"FALHA ao gravar em {celula}: {erro} "
                                  "(se houver célula em edição no Excel, pressione ESC)")
                    return Gravacao(celula, avisos)

                time.sleep(1)

        try:
            self.pasta.Save()
        except Exception as erro:
            avisos.append(f"{celula} preenchida, mas a planilha não foi salva: {erro}")

        return Gravacao(celula, avisos)


def _casar_cabecalhos(titulos: dict) -> dict:
    """Associa cada campo à primeira coluna cujo título bate com um dos apelidos."""
    colunas, usadas = {}, set()

    for campo, apelidos in CABECALHOS.items():
        achado = None

        for apelido in apelidos:
            for coluna, titulo in titulos.items():
                if coluna in usadas or not titulo:
                    continue

                if any(ruim in titulo for ruim in CABECALHOS_IGNORADOS):
                    continue

                if titulo == apelido or (len(apelido) > 2 and apelido in titulo):
                    achado = coluna
                    break

            if achado:
                break

        if achado:
            colunas[campo] = achado
            usadas.add(achado)

    return colunas

