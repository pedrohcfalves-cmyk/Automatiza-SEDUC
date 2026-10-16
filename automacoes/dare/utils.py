"""Funções puras (sem navegador): validação, datas, valores e nomes de arquivo."""

import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import config

MESES = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]


# ---- Documentos ---------------------------------------------------------------------------

def somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_cpf(texto: str) -> bool:
    d = somente_digitos(texto)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def validar_cnpj(texto: str) -> bool:
    d = somente_digitos(texto)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1

    def dv(base: str, pesos: list[int]) -> int:
        resto = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    return dv(d[:12], pesos1) == int(d[12]) and dv(d[:13], pesos2) == int(d[13])


def validar_processo(texto: str) -> str:
    """Número do processo SEI (ex.: 0012.123456/2026-12): exige ao menos 6 dígitos."""
    if len(somente_digitos(texto)) < 6:
        raise ValueError("Informe o número do processo (ex.: 0012.123456/2026-12).")
    return texto.strip()


def formatar_cpf(texto: str) -> str:
    d = somente_digitos(texto)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else texto


def formatar_cnpj(texto: str) -> str:
    d = somente_digitos(texto)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else texto


def mascarar_cpf(texto: str) -> str:
    """CPF para os logs: ***.456.789-** (evita gravar o CPF inteiro em arquivo de log)."""
    d = somente_digitos(texto)
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "***"


# ---- Datas --------------------------------------------------------------------------------

def proximo_dia_util(d: date) -> date:
    """Se cair em sábado ou domingo, avança para a segunda-feira (não considera feriados)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def vencimento_padrao(hoje: date | None = None) -> date:
    """Um mês depois de hoje, ajustado para um dia útil."""
    hoje = hoje or date.today()
    mes = hoje.month % 12 + 1
    ano = hoje.year + (1 if hoje.month == 12 else 0)
    dia = min(hoje.day, calendar.monthrange(ano, mes)[1])
    return proximo_dia_util(date(ano, mes, dia))


def ler_vencimento(texto: str) -> date:
    """Lê DD/MM/AAAA; se vazio, usa o vencimento padrão."""
    texto = texto.strip()
    if not texto:
        return vencimento_padrao()
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Data inválida. Use o formato DD/MM/AAAA.")


def validar_mes_ano(texto: str) -> str:
    """Aceita 102026 ou 10/2026 e devolve só os dígitos (MMAAAA)."""
    d = somente_digitos(texto)
    if len(d) != 6 or not 1 <= int(d[:2]) <= 12:
        raise ValueError("Informe o mês/ano como MMAAAA (ex.: 102026).")
    return d


def formatar_mes_ano(texto: str) -> str:
    d = somente_digitos(texto)
    return f"{d[:2]}/{d[2:]}" if len(d) == 6 else texto


# ---- Valores ------------------------------------------------------------------------------

def valor_para_digitos(texto: str) -> str:
    """
    Converte o valor digitado em centavos, sem vírgula (o site coloca a vírgula sozinho).
    '100,00' -> '10000' | '1.500,5' -> '150050' | '100' -> '10000'
    '7.243' (ponto como separador de milhar) -> '724300' | '100.5' -> '10050'
    """
    texto = (texto.strip() or config.VALOR_PADRAO).replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", texto):
        texto = texto.replace(".", "")  # '7.243' é sete mil duzentos e quarenta e três (milhar)
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise ValueError("Valor inválido. Exemplo: 100,00")
    if valor <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    return str(int((valor * 100).to_integral_value()))


def formatar_valor(texto: str) -> str:
    """'100' -> '100,00' | '1500,5' -> '1.500,50'."""
    centavos = int(valor_para_digitos(texto))
    inteiro, cent = divmod(centavos, 100)
    return f"{inteiro:,}".replace(",", ".") + f",{cent:02d}"


# ---- Arquivos -----------------------------------------------------------------------------

def nome_arquivo_seguro(texto: str) -> str:
    texto = re.sub(r'[<>:"/\\|?*]', "", texto)
    return re.sub(r"\s+", "_", texto.strip())[:80] or "SEM_NOME"


def caminho_sem_conflito(caminho: Path) -> Path:
    """Se o arquivo já existir, devolve 'nome (2).pdf', 'nome (3).pdf'... sem sobrescrever."""
    if not caminho.exists():
        return caminho
    n = 2
    while True:
        candidato = caminho.with_name(f"{caminho.stem} ({n}){caminho.suffix}")
        if not candidato.exists():
            return candidato
        n += 1
