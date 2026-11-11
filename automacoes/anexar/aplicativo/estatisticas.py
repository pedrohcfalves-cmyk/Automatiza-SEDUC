"""
As contas das telas Estatísticas e Relatório do mês, e as planilhas (CSV que abre no Excel em português).

Sem janela e sem Qt: recebe as execuções (metricas.ler_execucoes) e as estimativas (minutos à mão por item)
e devolve números. Dá para testar sozinho (testes/test_aplicativo.py).

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import json
import re
from datetime import datetime, timedelta

from automacoes.anexar.aplicativo.metricas import CATEGORIAS, ETAPAS
from automacoes.anexar.versao import NOME_APLICATIVO, VERSAO

ETAPAS_CHAVES = [chave for chave, _nome in ETAPAS]
NOME_ETAPA = {
    "LOGIN": "Entrar no SEI e no SIGEF",
    "SEI1": "Dados do processo (SEI)",
    "CE": "CE — Despesa Certificada",
    "NL": "NL — Nota de Lançamento",
    "PP": "PP — Preparação de Pagamento",
    "OB": "OB — Ordem Bancária",
    "BAIXAR": "Baixar os documentos do SIGEF",
    "SEI": "Colocar os documentos no processo (SEI)",
}
NOME_CURTO_ETAPA = {
    "SEI1": "Conferência — dados no SEI", "CE": "CE — Despesa Certificada", "NL": "NL — Nota de Lançamento",
    "PP": "PP — Preparação de Pagamento", "OB": "OB — Ordem Bancária", "BAIXAR": "Baixar — documentos do SIGEF",
    "SEI": "SEI — colocar no processo",
}
NOME_CURTO_CATEGORIA = {"CONFERENCIA": "Conferência", "ANEXAR": "Anexar no SEI"}
SITUACAO = {
    "concluido": ("Concluído", "ok"),
    "pendente": ("Faltou algo", "pendente"),
    "erro": ("Parou com erro", "erro"),
    "interrompido": ("Parado por você", "interrompido"),
}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
PERIODOS = [("mes", "Este mês"), ("30", "Últimos 30 dias"), ("ano", "Este ano"), ("tudo", "Todo o período")]


def data_de(execucao: dict):
    try:
        return datetime.fromisoformat(str(execucao.get("inicio")).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def no_periodo(execucoes: list, periodo: str, agora: datetime = None) -> list:
    agora = agora or datetime.now()
    escolhidas = []
    for execucao in execucoes:
        data = data_de(execucao)
        if data is None:
            if periodo == "tudo":
                escolhidas.append(execucao)
            continue
        if periodo == "mes" and (data.year, data.month) != (agora.year, agora.month):
            continue
        if periodo == "ano" and data.year != agora.year:
            continue
        if periodo == "30" and agora - data > timedelta(days=30):
            continue
        escolhidas.append(execucao)
    return escolhidas


def etapa_de(execucao: dict, chave: str):
    return next((e for e in execucao.get("etapas") or [] if e.get("chave") == chave), None)


def _soma(valores) -> float:
    total = 0.0
    for valor in valores:
        try:
            total += float(valor or 0)
        except (TypeError, ValueError):
            pass
    return total


def calcular_economia(execucoes: list, estimativas: dict) -> dict:
    """Itens, tempo com o aplicativo e tempo à mão de cada tipo de automação (e o total)."""
    linhas = []
    for categoria in CATEGORIAS:
        itens = tempo = humano = 0.0
        for execucao in execucoes:
            for chave in categoria["etapas"]:
                etapa = etapa_de(execucao, chave)
                if etapa:
                    tempo += etapa.get("duracao_s") or 0
                    humano += etapa.get("humano_s") or 0
            novos = execucao.get("novos") or {}
            terminou = execucao.get("situacao") in ("concluido", "pendente")
            sigla = categoria["chave"]
            if sigla in ("CE", "NL", "PP", "OB"):
                itens += novos.get(sigla.lower()) or 0
            elif sigla == "CONFERENCIA":
                itens += 1 if etapa_de(execucao, "SEI1") and (terminou or len(execucao.get("etapas") or []) > 1) else 0
            elif sigla == "ANEXAR":
                itens += 1 if etapa_de(execucao, "SEI") and terminou else 0
        try:
            minutos = float(estimativas.get(categoria["chave"]) or 0)
        except (TypeError, ValueError):
            minutos = 0.0
        mao = itens * minutos * 60
        linhas.append({**categoria, "itens": itens, "tempo": tempo, "humano": humano, "mao": mao,
                       "economizado": mao - tempo, "minutos": minutos})
    total = {"itens": _soma(l["itens"] for l in linhas), "tempo": _soma(l["tempo"] for l in linhas),
             "humano": _soma(l["humano"] for l in linhas), "mao": _soma(l["mao"] for l in linhas)}
    total["economizado"] = total["mao"] - total["tempo"]
    return {"linhas": linhas, "total": total}


def projecao(execucoes: list, estimativas: dict, quantidade: int):
    """Quanto levaria `quantidade` processos por mês, com a média dos processos terminados. None se não há nenhum."""
    validas = [e for e in execucoes if e.get("situacao") in ("concluido", "pendente")]
    if not validas:
        return None
    total = calcular_economia(validas, estimativas)["total"]
    quantidade = max(1, int(quantidade or 1))
    por = {"app": total["tempo"] / len(validas), "humano": total["humano"] / len(validas),
           "mao": total["mao"] / len(validas)}
    return {"mao": por["mao"] * quantidade, "app": por["app"] * quantidade, "humano": por["humano"] * quantidade,
            "economia": max(0.0, (por["mao"] - por["app"]) * quantidade)}


def chave_mes(data: datetime) -> str:
    return f"{data.year}-{data.month:02d}"


def nome_mes(chave: str) -> str:
    ano, mes = chave.split("-")
    return f"{MESES[int(mes) - 1]} de {ano}"


def meses_disponiveis(execucoes: list, agora: datetime = None) -> list:
    meses = {chave_mes(agora or datetime.now())}
    for execucao in execucoes:
        data = data_de(execucao)
        if data:
            meses.add(chave_mes(data))
    return sorted(meses, reverse=True)


def execucoes_do_mes(execucoes: list, mes: str) -> list:
    return [e for e in execucoes if data_de(e) and chave_mes(data_de(e)) == mes]


def detalhe_do_mes(execucoes: list) -> list:
    detalhe = []
    for chave in ETAPAS_CHAVES:
        com_etapa = [e for e in execucoes if etapa_de(e, chave)]
        tempo = _soma(etapa_de(e, chave).get("duracao_s") for e in com_etapa)
        humano = _soma(etapa_de(e, chave).get("humano_s") for e in com_etapa)
        if chave in ("CE", "NL", "PP", "OB"):
            itens = _soma((e.get("novos") or {}).get(chave.lower()) for e in execucoes)
        elif chave == "BAIXAR":
            itens = _soma((e.get("documentos") or {}).get("baixados") for e in com_etapa)
        else:
            itens = len(com_etapa)
        detalhe.append({"chave": chave, "nome": NOME_CURTO_ETAPA.get(chave, chave), "execucoes": len(com_etapa),
                        "itens": itens, "tempo": tempo, "humano": humano})
    return detalhe


# ============================================================ planilhas (Excel em português)


def _celula(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, (int, float)):
        return str(round(valor * 100) / 100).rstrip("0").rstrip(".").replace(".", ",") if isinstance(valor, float) \
            else str(valor)
    texto = str(valor)
    return '"' + texto.replace('"', '""') + '"' if re.search(r'[;"\n]', texto) else texto


def planilha(cabecalho: list, linhas: list) -> str:
    """CSV com ';' e vírgula decimal, com BOM (o Excel abre em português sem pedir nada)."""
    texto = "\r\n".join(";".join(_celula(c) for c in linha) for linha in [cabecalho, *linhas])
    return "﻿" + texto + "\r\n"


def _fatia(valor, divisor):
    return None if valor is None else valor / divisor


def planilha_processos(execucoes: list, anonimo: bool) -> str:
    cab = ["id", "versao", "inicio", "fim", "situacao", *([] if anonimo else ["processo"]), "lancamentos",
           "valor_total_reais", "tempo_total_min", "esperando_voce_min", "maquina_min", "respostas",
           "ce_reaproveitada", "novos_ce", "novos_nl", "novos_pp", "novos_ob", "docs_baixados", "erros"]
    linhas = []
    for e in execucoes:
        novos, docs = e.get("novos") or {}, e.get("documentos") or {}
        linhas.append([e.get("id"), e.get("versao"), e.get("inicio"), e.get("fim"), e.get("situacao"),
                       *([] if anonimo else [e.get("processo")]), e.get("lancamentos"),
                       _fatia(e.get("valor_total_centavos"), 100), _fatia(e.get("duracao_s"), 60),
                       _fatia(e.get("humano_s"), 60), _fatia(e.get("maquina_s"), 60), e.get("respostas"),
                       e.get("ce_reaproveitada"), novos.get("ce"), novos.get("nl"), novos.get("pp"),
                       novos.get("ob"), docs.get("baixados"),
                       " | ".join(f"{x.get('etapa') or ''}: {x.get('titulo')}" for x in e.get("erros") or [])])
    return planilha(cab, linhas)


def planilha_etapas(execucoes: list, anonimo: bool) -> str:
    cab = ["id_execucao", "inicio", "versao", "situacao", *([] if anonimo else ["processo"]), "etapa", "etapa_nome",
           "duracao_s", "esperando_voce_s", "maquina_s", "respostas"]
    linhas = [[e.get("id"), e.get("inicio"), e.get("versao"), e.get("situacao"), *([] if anonimo else [e.get("processo")]),
               et.get("chave"), NOME_ETAPA.get(et.get("chave"), et.get("chave")), et.get("duracao_s"),
               et.get("humano_s"), et.get("maquina_s"), et.get("respostas")]
              for e in execucoes for et in e.get("etapas") or []]
    return planilha(cab, linhas)


def planilha_economia(execucoes: list, estimativas: dict) -> str:
    conta = calcular_economia(execucoes, estimativas)

    def pct(a, b):
        return a / b * 100 if b else None

    cab = ["tipo", "minutos_a_mao_por_item", "itens", "com_aplicativo_min", "esperando_voce_min",
           "a_mao_estimado_min", "economizado_min", "economia_percentual"]
    linhas = [[l["nome"], l["minutos"], l["itens"], l["tempo"] / 60, l["humano"] / 60, l["mao"] / 60,
               l["economizado"] / 60, pct(l["economizado"], l["mao"])] for l in conta["linhas"]]
    t = conta["total"]
    linhas.append(["Total", None, t["itens"], t["tempo"] / 60, t["humano"] / 60, t["mao"] / 60,
                   t["economizado"] / 60, pct(t["economizado"], t["mao"])])
    return planilha(cab, linhas)


def planilha_do_mes(execucoes: list, mes: str) -> str:
    cab = ["mes", "etapa", "execucoes", "itens_processados", "tempo_total_min", "media_por_item_min", "esperando_voce_min"]
    linhas = [[nome_mes(mes), d["nome"], d["execucoes"], d["itens"], d["tempo"] / 60,
               d["tempo"] / d["itens"] / 60 if d["itens"] else None, d["humano"] / 60]
              for d in detalhe_do_mes(execucoes)]
    return planilha(cab, linhas)


def dados_completos(execucoes: list, estimativas: dict, periodo: str, anonimo: bool) -> str:
    itens = [{chave: valor for chave, valor in e.items() if not (anonimo and chave == "processo")} for e in execucoes]
    return json.dumps({"aplicativo": NOME_APLICATIVO, "versao": VERSAO, "exportado_em": datetime.now().isoformat(),
                       "periodo": periodo, "anonimo": anonimo, "estimativas_minutos": estimativas,
                       "execucoes": itens}, ensure_ascii=False, indent=2)
