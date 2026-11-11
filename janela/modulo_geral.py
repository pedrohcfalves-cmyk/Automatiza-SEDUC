"""
O que vale para todas as automações (menu da barra lateral e do topo)
(janela/interface/central.js), por UMA porta: chamar(acao, dados) -- Api.geral.

    Ano do SIGEF          o exercício usado pela OB e pela NE (automacoes/geral.py).
                          Padrão: o ano atual.
    Relatório geral       TODAS as automações numa página: tempo economizado no total,
                          por mês, por pessoa e o detalhe de cada uma (automacoes/painel.py).
    Entrar nos sistemas   antes de começar o DARE ou o BB (as que não tinham esse passo):
                          abre o Chrome da automação SÓ com as abas dela e guarda que a
                          pessoa confirmou o login (central.js, lbaLogin).
"""
import os
from datetime import date

from automacoes import geral, painel
from janela import modulos_janela

# As pastas de outras pessoas incluídas no painel ficam no config.json.
CHAVE_PASTAS = "painel_pastas"
CHAVES_MINUTOS = {"OB": "minutos_manual_por_ob", "NE": "minutos_manual_por_ne", "DARE": "minutos_manual_por_dare"}

_janela = {"obter": lambda: None}


def configurar(janela) -> None:
    _janela["obter"] = janela


# ---------------------------------------------------------- Ano do SIGEF


def _ano() -> dict:
    return {"ok": True, "ano": geral.ano_sigef(), "atual": geral.ano_atual(), "anos": geral.anos_possiveis()}


def _definir_ano(d: dict) -> dict:
    # Trocar no meio de um download mudaria o endereço com a automação andando.
    if not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
        return {**_ano(), "ok": False, "erro": "Há uma automação rodando. Espere ela terminar para trocar o ano."}
    try:
        geral.definir_ano_sigef(d.get("ano"))
    except ValueError as erro:
        return {**_ano(), "ok": False, "erro": str(erro)}
    finally:
        modulos_janela.USO_DO_CHROME.release()
    ano = geral.ano_sigef()
    print(f"📅 Ano do SIGEF: {ano}" + ("" if ano == geral.ano_atual() else " (escolhido; o ano atual é outro)"))
    return _ano()


# ----------------------------------------------------- Painel de resultados


def _pastas() -> list[dict]:
    pastas = [p for p in geral.ler_config().get(CHAVE_PASTAS) or [] if isinstance(p, str)]
    return [{"caminho": p, "pessoa": painel.pessoa_do_caminho(p), "existe": os.path.isdir(p)} for p in pastas]


def _opcoes() -> dict:
    config = geral.ler_config()
    hoje = date.today()
    return {
        "ok": True, "de": date(hoje.year, 1, 1).isoformat(), "ate": hoje.isoformat(),
        "minutos": {a: config.get(chave, painel.MINUTOS_PADRAO[a]) for a, chave in CHAVES_MINUTOS.items()},
        "eu": painel.pessoa_atual(), "pastas": _pastas(),
    }


def _incluir(caminho: str) -> dict:
    fonte = painel.fonte_da_pasta(caminho)
    if not painel.tem_dados(fonte):
        return {"ok": False, "pastas": _pastas(),
                "erro": "Nessa pasta não há resultados das automações (pasta metricas, dados\\desempenho.csv "
                        "ou relatorios\\execucoes.jsonl)."}
    pastas = [p["caminho"] for p in _pastas()]
    if caminho not in pastas:
        geral.gravar_config(**{CHAVE_PASTAS: pastas + [caminho]})
    return {"ok": True, "pastas": _pastas()}


def _escolher_pasta() -> dict:
    import webview

    escolhida = _janela["obter"]().create_file_dialog(webview.FileDialog.FOLDER)
    if not escolhida:
        return {"ok": False, "cancelou": True}
    return _incluir(escolhida[0] if isinstance(escolhida, (list, tuple)) else escolhida)


def _remover_pasta(d: dict) -> dict:
    pastas = [p["caminho"] for p in _pastas() if p["caminho"] != d.get("caminho")]
    geral.gravar_config(**{CHAVE_PASTAS: pastas or None})
    return {"ok": True, "pastas": _pastas()}


def _gerar(d: dict) -> dict:
    try:
        inicio, fim = date.fromisoformat(d.get("de") or ""), date.fromisoformat(d.get("ate") or "")
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Confira as datas do período."}
    try:
        minutos = painel.minutos_validos(d.get("minutos"))
    except ValueError as erro:
        return {"ok": False, "erro": str(erro)}
    geral.gravar_config(**{CHAVES_MINUTOS[a]: minutos[a] for a in painel.COM_MINUTOS})
    fontes = painel.fontes_padrao() + [painel.fonte_da_pasta(p["caminho"]) for p in _pastas() if p["existe"]]
    try:
        caminho = painel.gerar(inicio, fim, minutos, fontes)
    except Exception as erro:  # planilha de resultados travada/corrompida
        return {"ok": False, "erro": f"Não consegui montar o relatório: {erro}"}
    os.startfile(caminho)
    return {"ok": True, "caminho": caminho}


# ---------------------------------------------- Entrar nos sistemas antes de começar


def _sistemas(automacao: str) -> list[tuple[str, str, str]]:
    """(nome na tela, domínio, endereço) das abas que a automação usa -- e só elas."""
    from automacoes.sigef_sei import preparar_navegador as pn

    if automacao == "dare":
        from automacoes.dare import config as dare

        return [("DARE", dare.HOST_DARE, dare.URL_DARE), ("SEI", dare.HOST_SEI, dare.URL_SEI)]
    if automacao == "bb":  # o SEI é onde o BB anexa os saldos
        return [("Banco do Brasil", pn.DOMINIO_BB, pn.URL_BB_LOGIN), ("SEI", pn.DOMINIO_SEI, pn.URL_SEI)]
    raise ValueError(f"Automação sem a etapa de login: {automacao}")


# Quem já confirmou o login nesta sessão da janela (como o DARE fazia: uma vez só).
_confirmados: set = set()


def _login_estado(d: dict) -> dict:
    from automacoes.sigef_sei import preparar_navegador as pn

    automacao = d.get("automacao", "")
    nomes = [nome for nome, _, _ in _sistemas(automacao)]
    if not pn.porta_ja_esta_em_uso(pn.PORTA_PADRAO):
        _confirmados.discard(automacao)  # o Chrome foi fechado: entrar de novo
    return {"ok": True, "sistemas": nomes, "confirmado": automacao in _confirmados}


def _abrir_abas(d: dict) -> dict:
    from automacoes.sigef_sei import preparar_navegador as pn

    sistemas = _sistemas(d.get("automacao", ""))
    try:
        pn.abrir_abas_sem_conectar([(dominio, url) for _, dominio, url in sistemas])
    except SystemExit as erro:  # achar_chrome: sem o Chrome, a mensagem de como instalar
        return {"ok": False, "erro": str(erro.code).strip()}
    except Exception as erro:  # noqa: BLE001 - vai para a tela, com o "Tentar de novo"
        return {"ok": False, "erro": f"Não consegui abrir o navegador da automação: {erro}"}
    return {"ok": True, "sistemas": [nome for nome, _, _ in sistemas]}


def _login_confirmado(d: dict) -> dict:
    automacao = d.get("automacao", "")
    _sistemas(automacao)  # só as automações conhecidas
    _confirmados.add(automacao)
    if automacao == "dare":  # o DARE não pergunta de novo no meio da execução
        from automacoes.dare import motor

        motor._sessao["login_confirmado"] = True
    return {"ok": True}


def chamar(acao: str, dados: dict | None = None) -> dict:
    """A porta única do menu do topo (central.js)."""
    d = dados or {}
    acoes = {
        "ano": _ano,
        "definir_ano": lambda: _definir_ano(d),
        "painel_opcoes": _opcoes,
        "painel_incluir_pasta": _escolher_pasta,
        "painel_remover_pasta": lambda: _remover_pasta(d),
        "painel_gerar": lambda: _gerar(d),
        "login_estado": lambda: _login_estado(d),
        "abrir_abas": lambda: _abrir_abas(d),
        "login_confirmado": lambda: _login_confirmado(d),
    }
    if acao not in acoes:
        return {"ok": False, "erro": f"Ação desconhecida: {acao}"}
    return acoes[acao]()
