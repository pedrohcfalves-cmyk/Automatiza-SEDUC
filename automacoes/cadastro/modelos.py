"""Estruturas de dados e validação de um lote de cadastro."""

import re
from dataclasses import dataclass
from enum import Enum

from .bancos import resolver_banco

ROTULOS = {
    "cpf": "CPF",
    "nome": "Nome",
    "banco": "Código do Banco",
    "agencia": "Agência",
    "conta": "Conta",
}

# Agência e conta vão ao SIGEF como estão escritas: letras, números, "-" e "."
# (o dígito verificador pode vir separado por traço e pode ser letra, como X ou P)
CAMPOS_BANCARIOS = ("agencia", "conta")
FORA_DO_BANCARIO = re.compile(r"[^0-9A-Z.\-]")

TAMANHO_CPF = 11


class ReiniciarLote(Exception):
    """Usuário reprovou os dados: corrigir e refazer somente este lote."""


class PularLote(Exception):
    """Usuário optou por descartar este lote/linha."""


class Resposta(Enum):
    """Respostas possíveis na conferência manual de uma ação."""

    SIM = "s"
    SIM_TODOS = "t"  # confirma e não pergunta mais neste lote
    CORRIGIR = "n"
    PULAR = "p"


@dataclass
class Lote:
    """Um credor e seu domicílio bancário."""

    cpf: str = ""
    nome: str = ""
    banco: str = ""
    agencia: str = ""
    conta: str = ""

    def __str__(self) -> str:
        return " | ".join(f"{ROTULOS[campo]}: {getattr(self, campo)}" for campo in ROTULOS)

    def faltando(self) -> list:
        """Rótulos dos campos vazios."""
        return [ROTULOS[campo] for campo in ROTULOS if not getattr(self, campo)]

    def cpf_valido(self) -> bool:
        return len(self.cpf) == TAMANHO_CPF


def cpf_confere(cpf: str) -> bool:
    """Confere os dígitos verificadores (ajuda a pegar erro de digitação)."""
    if len(cpf) != TAMANHO_CPF or not cpf.isdigit() or cpf == cpf[0] * TAMANHO_CPF:
        return False

    for tamanho in (9, 10):
        soma = sum(int(digito) * peso for digito, peso in zip(cpf, range(tamanho + 1, 1, -1)))

        if soma * 10 % 11 % 10 != int(cpf[tamanho]):
            return False

    return True


def limpar(campo: str, valor: str) -> str:
    """Normaliza o valor de um campo conforme a sua natureza."""
    valor = (valor or "").strip()

    if campo == "banco":
        return resolver_banco(valor)

    if campo in CAMPOS_BANCARIOS:
        # Só saem espaços e símbolos estranhos; letras (em maiúscula), números, "-" e "." ficam
        return FORA_DO_BANCARIO.sub("", valor.upper())

    if campo != "cpf":
        return valor

    valor = re.sub(r"\D", "", valor)

    # O Excel come o zero à esquerda do CPF
    if 0 < len(valor) < TAMANHO_CPF:
        valor = valor.zfill(TAMANHO_CPF)

    return valor


def lote_de_linha(linha: str) -> Lote:
    """Converte 'CPF,Nome,Banco,Agência,Conta' em um Lote validado."""
    separador = ";" if ";" in linha else ("\t" if "\t" in linha else ",")
    partes = [parte.strip() for parte in linha.split(separador)]

    if len(partes) != len(ROTULOS):
        raise ValueError(f"esperado {len(ROTULOS)} campos, encontrado {len(partes)}")

    lote = Lote(**{campo: limpar(campo, valor) for campo, valor in zip(ROTULOS, partes)})

    if partes[2] and not lote.banco:
        raise ValueError(f"banco não reconhecido: {partes[2]}")

    if lote.faltando():
        raise ValueError("campos vazios: " + ", ".join(lote.faltando()))

    if not lote.cpf_valido():
        raise ValueError(f"CPF deve ter {TAMANHO_CPF} dígitos")

    return lote


def lotes_de_texto(texto: str) -> tuple:
    """Lê várias linhas; devolve (lotes, [(nº da linha, motivo)] das ignoradas)."""
    lotes, ignoradas = [], []

    for numero, linha in enumerate(texto.splitlines(), 1):
        linha = linha.strip()

        # Linha vazia ou cabeçalho do arquivo
        if not linha or linha.lower().startswith("cpf"):
            continue

        try:
            lotes.append(lote_de_linha(linha))
        except ValueError as erro:
            ignoradas.append((numero, str(erro)))

    return lotes, ignoradas


def ler_arquivo_lotes(caminho: str) -> tuple:
    """Lê um .csv/.txt em UTF-8 ou no padrão do Excel brasileiro (cp1252)."""
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read()

    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252")

    return lotes_de_texto(texto)
