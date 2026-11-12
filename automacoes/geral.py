"""
Configurações gerais, que valem para todas as automações.

    PASTA_DADOS              a pasta de dados (Documentos\\Automacao SIGEF-SEI, ou LBA_PASTA_DADOS)
    ano_sigef()              o exercício do SIGEF em uso: o escolhido pela pessoa, ou o ano atual
    url_sigef(tela)          o endereço de uma tela do SIGEF nesse exercício
    definir_ano_sigef(ano)   troca o exercício (na janela: rodapé da barra lateral)

O SIGEF tem um endereço por exercício (.../SIGEF2026/...). As telas da OB e da NE
são montadas com url_sigef(); a NE também confere se o número é desse exercício.
O padrão é o ano atual. A pessoa pode escolher outro -- em janeiro, se o SIGEF ainda
não virou, por exemplo --, e a escolha fica em <pasta de dados>/config.json
("ano_sigef"). Escolher de novo o ano atual apaga a escolha: no ano seguinte o padrão
volta a valer sozinho, sem ninguém precisar lembrar.

O DARE e o BB não dependem do exercício do SIGEF (o DARE pede o mês/ano de
referência em cada lançamento; o BB não usa ano).
"""
import json
import os
import re
import sys
from datetime import date

PASTA_DADOS = os.environ.get("LBA_PASTA_DADOS") or os.path.join(
    os.path.expanduser("~"), "Documents", "Automacao SIGEF-SEI"
)
CAMINHO_CONFIG = os.path.join(PASTA_DADOS, "config.json")
# A pasta dados\ do Gerar pagamento (Anexar Documentos), fora da pasta do programa. Fica aqui porque
# duas partes leem: a janela dele (janela/modulo_anexar.py) e o relatório geral (automacoes/painel.py).
PASTA_DADOS_ANEXAR = os.path.join(os.path.expanduser("~"), "Documents", "Anexar Documentos")

CHAVE_ANO = "ano_sigef"
PRIMEIRO_ANO = 2020

# A parte do endereço que muda com o exercício (produção e homologação).
_ANO_NA_URL = re.compile(r"(sigef(?:hom)?\.sefin\.ro\.gov\.br/SIGEF)\d{4}/", re.IGNORECASE)


def gravar_json(caminho: str, dados) -> None:
    """Grava de forma atômica (temporário + os.replace): queda no meio não deixa o JSON pela metade."""
    temporario = f"{caminho}.tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    os.replace(temporario, caminho)


def ler_config() -> dict:
    try:
        with open(CAMINHO_CONFIG, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def gravar_config(**valores) -> None:
    """Junta os valores ao config.json (o que já estava lá continua; None apaga a chave)."""
    config = ler_config()
    for chave, valor in valores.items():
        if valor is None:
            config.pop(chave, None)
        else:
            config[chave] = valor
    os.makedirs(PASTA_DADOS, exist_ok=True)
    gravar_json(CAMINHO_CONFIG, config)


def ano_atual() -> int:
    return date.today().year


def anos_possiveis() -> list[int]:
    return list(range(PRIMEIRO_ANO, ano_atual() + 2))


def ano_sigef() -> int:
    """O exercício escolhido, ou o ano atual (sem escolha, ou com uma escolha inválida)."""
    try:
        escolhido = int(ler_config().get(CHAVE_ANO) or 0)
    except (TypeError, ValueError):
        escolhido = 0
    return escolhido if escolhido in anos_possiveis() else ano_atual()


def url_sigef(tela: str) -> str:
    """'FIN/FINListarOrdemBancaria.aspx?...' -> 'http://sigef.sefin.ro.gov.br/SIGEF2026/FIN/...'"""
    return f"http://sigef.sefin.ro.gov.br/SIGEF{ano_sigef()}/{tela}"


def definir_ano_sigef(ano) -> int:
    """Grava a escolha e já troca o exercício nos endereços carregados. ValueError se o ano não servir."""
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        raise ValueError(f"Ano inválido: {ano!r}") from None
    if ano not in anos_possiveis():
        raise ValueError(f"Escolha um ano entre {PRIMEIRO_ANO} e {ano_atual() + 1}.")
    gravar_config(**{CHAVE_ANO: None if ano == ano_atual() else ano})
    _aplicar(ano)
    return ano


def _aplicar(ano: int) -> None:
    """
    Troca o exercício nos endereços do SIGEF que já estão na memória: as constantes
    dos módulos e as cópias que outros módulos importaram pelo nome (from x import
    URL_...), além do ANO_SIGEF da NE. Assim a troca vale na hora, sem reabrir.
    """
    texto = str(ano)
    for nome, modulo in list(sys.modules.items()):
        if modulo is None or not (nome.startswith(("automacoes.", "janela.")) or nome in ("app_janela", "main")):
            continue
        for atributo, valor in list(vars(modulo).items()):
            if not isinstance(valor, str):
                continue
            if atributo == "ANO_SIGEF":
                setattr(modulo, atributo, texto)
            elif _ANO_NA_URL.search(valor):
                setattr(modulo, atributo, _ANO_NA_URL.sub(rf"\g<1>{texto}/", valor))
