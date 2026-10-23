"""
Quais documentos da OB baixar do SIGEF e anexar no SEI.

Na janela, o passo "3 Processo e OB" tem uma caixa para cada tipo
(CE, NL, PP e OB), todas marcadas por padrão. O que fica marcado chega
aqui como uma lista de siglas e passa por:

    baixar_documentos(..., documentos=...)   não abre/baixa o que não foi marcado
    executar_sei2(..., documentos=...)       não anexa o que não foi marcado

Sem `documentos` (None) vale TUDO -- é o comportamento de sempre, e é o
que o main.py (tela preta) e quem chama sem saber da escolha recebem.

Este arquivo não importa nada das etapas de propósito: as duas importam
daqui, sem import circular.
"""

# Na ordem em que entram no SEI... menos a OB, que vai por último lá;
# aqui a ordem só serve para mostrar e gravar sempre igual.
DOCUMENTOS = ("CE", "NL", "PP", "OB")

NOMES = {
    "CE": "Despesa Certificada",
    "NL": "Nota de Lançamento",
    "PP": "Preparação de Pagamento",
    "OB": "Ordem Bancária",
}


def normalizar_documentos(documentos=None) -> tuple:
    """
    A escolha como tupla ordenada de siglas válidas.

    None (ninguém escolheu nada) vale todos. Siglas desconhecidas são
    ignoradas; uma lista que fica vazia depois disso também vale todos,
    para nunca rodar uma OB "sem documento nenhum" por engano -- quem
    pede a escolha (a janela) já impede a lista vazia antes.
    """
    if documentos is None:
        return DOCUMENTOS
    pedidos = {str(d).strip().upper() for d in documentos}
    escolhidos = tuple(d for d in DOCUMENTOS if d in pedidos)
    return escolhidos or DOCUMENTOS


def todos(documentos) -> bool:
    """True se a escolha inclui os quatro tipos (o fluxo de sempre)."""
    return set(normalizar_documentos(documentos)) == set(DOCUMENTOS)


def descrever(documentos) -> str:
    """'CE, NL, PP e OB' / 'PP e OB' / 'OB' -- para as mensagens."""
    siglas = list(normalizar_documentos(documentos))
    return siglas[0] if len(siglas) == 1 else ", ".join(siglas[:-1]) + " e " + siglas[-1]


def filtrar_pacote(dados: dict, documentos) -> dict:
    """
    Cópia do pacote do download (o que baixar_documentos devolve) só com
    os arquivos dos tipos escolhidos. Não mexe no original -- ele é o
    mesmo que fica gravado na sessão.

    Os lançamentos (um por PP) continuam todos: só perdem os arquivos dos
    tipos não escolhidos. O número da CE/NL fica, para o resumo.
    """
    if dados is None:
        return None
    escolhidos = set(normalizar_documentos(documentos))
    copia = dict(dados)
    if "CE" not in escolhidos:
        copia["grupos_ce"] = []
    if "OB" not in escolhidos:
        copia["arquivos_ob"] = []

    lancamentos = []
    for item in dados.get("lancamentos") or []:
        item = dict(item)
        if "CE" not in escolhidos:
            item["arquivos_ce"] = []
        if "NL" not in escolhidos:
            item["arquivos_nl"] = []
        if "PP" not in escolhidos:
            item["arquivos_pp"] = []
        item["arquivos_anexar"] = (
            (item.get("arquivos_ce") or []) + (item.get("arquivos_nl") or []) + (item.get("arquivos_pp") or [])
        )
        lancamentos.append(item)
    copia["lancamentos"] = lancamentos
    if "NL" not in escolhidos:
        # Aviso de NL que deu erro no SIGEF não vale se a NL nem foi pedida.
        copia["avisos_download"] = [
            a for a in (dados.get("avisos_download") or []) if not a.startswith("NL")
        ]
    copia["documentos"] = list(normalizar_documentos(documentos))
    return copia
