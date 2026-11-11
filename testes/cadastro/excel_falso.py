"""Imitação mínima do Excel via COM, para testar o modo planilha sem Windows."""

import re

LINHAS_EXCEL = 1_048_576


def _letra(indice: int) -> str:
    letra = ""

    while indice:
        indice, resto = divmod(indice - 1, 26)
        letra = chr(65 + resto) + letra

    return letra


def _indice(letra: str) -> int:
    indice = 0

    for caractere in letra:
        indice = indice * 26 + ord(caractere) - 64

    return indice


class _Coluna:
    def __init__(self, oculta: bool):
        self.Hidden = oculta


class Celula:
    MergeCells = False

    def __init__(self, aba, linha: int, coluna: int):
        self.aba, self.Row, self.Column = aba, linha, coluna

    @property
    def Value(self):
        return self.aba.dados.get((self.Row, self.Column))

    @Value.setter
    def Value(self, valor):
        self.aba.dados[(self.Row, self.Column)] = valor

    @property
    def Address(self) -> str:
        return f"${_letra(self.Column)}${self.Row}"

    @property
    def EntireColumn(self):
        return _Coluna(self.Column in self.aba.colunas_ocultas)

    def End(self, _direcao):
        linhas = [l for (l, c), v in self.aba.dados.items()
                  if c == self.Column and v not in (None, "")]
        return Celula(self.aba, max(linhas, default=1), self.Column)


class Faixa:
    def __init__(self, aba, inicio: Celula, fim: Celula):
        self.aba, self.inicio, self.fim = aba, inicio, fim

    @property
    def Value(self):
        linhas = range(self.inicio.Row, self.fim.Row + 1)
        colunas = range(self.inicio.Column, self.fim.Column + 1)

        if len(linhas) == 1 and len(colunas) == 1:
            return self.inicio.Value

        return tuple(tuple(self.aba.dados.get((l, c)) for c in colunas) for l in linhas)


class _Linhas:
    Count = LINHAS_EXCEL


class Aba:
    Rows = _Linhas()

    def __init__(self, nome: str, linhas: list = (), inicio: int = 1):
        self.Name = nome
        self.dados = {}
        self.colunas_ocultas = set()

        for numero, valores in enumerate(linhas, inicio):
            for coluna, valor in enumerate(valores, 1):
                if valor not in (None, ""):
                    self.dados[(numero, coluna)] = valor

    def Cells(self, linha: int, coluna: int) -> Celula:
        return Celula(self, linha, coluna)

    def Range(self, inicio, fim=None):
        if isinstance(inicio, str):
            letra, linha = re.fullmatch(r"([A-Z]+)(\d+)", inicio.upper()).groups()
            return Celula(self, int(linha), _indice(letra))

        return Faixa(self, inicio, fim)

    def valor(self, endereco: str):
        return self.Range(endereco).Value


class _Abas:
    def __init__(self, abas):
        self._abas = list(abas)

    def __iter__(self):
        return iter(self._abas)

    def __call__(self, chave):
        if isinstance(chave, int):
            return self._abas[chave - 1]

        return next(aba for aba in self._abas if aba.Name == chave)


class Pasta:
    def __init__(self, nome: str, abas, somente_leitura: bool = False):
        self.Name = nome
        self.FullName = f"C:\\Planilhas\\{nome}"
        self.ReadOnly = somente_leitura
        self.Worksheets = _Abas(abas)
        self.salvamentos = 0

    def Save(self):
        self.salvamentos += 1


class _Pastas:
    def __init__(self, pastas):
        self._pastas = list(pastas)

    def __iter__(self):
        return iter(self._pastas)

    def __call__(self, indice: int):
        return self._pastas[indice - 1]

    def Open(self, caminho: str):
        raise OSError(f"arquivo não encontrado: {caminho}")


class Excel:
    def __init__(self, *pastas):
        self.Workbooks = _Pastas(pastas)
        self.ActiveWorkbook = pastas[0] if pastas else None
