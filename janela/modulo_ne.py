"""
A Nota de Empenho (NE) dentro da janela: o módulo "Nota de Empenho" da barra lateral.

A automação é a de automacoes/ne/, sem mudança. Aqui fica só a ligação com a página
(janela/interface/ne.js), no mesmo modelo do DARE (modulo_dare.py):

    a página chama tudo por UMA porta, chamar(acao, dados)     (Api.ne do app_janela)
    o Python avisa a página pelos eventos "ne_*"

SEPARADA DA OB: a NE não usa nenhuma tela, estado nem lista do módulo "Anexar no
SEI" (a Ordem Bancária). O que as duas dividem é só o que não dá para separar:

    o Chrome da automação e o login     (o mesmo perfil, C:\\ChromeAutomacao)
    o Trabalhador do app_janela         (a única thread que fala com o Chrome:
                                         o Playwright não aceita outra) -- ele chama
                                         executar() para os comandos "ne_*"
    USO_DO_CHROME                       (uma automação por vez)
"""
import os
from datetime import date

from automacoes.geral import pode_abrir
from automacoes.ne import __version__, etapa, lote, relatorio
from automacoes.sigef_sei.etapa_listar_baixar import PASTA_BASE, carregar_sessao, normalizar_processo_sei
from automacoes.sigef_sei.preparar_navegador import DOMINIO_SIGEF, _garantir_url_certa

# Os comandos do Trabalhador que mexem no SIGEF/SEI (os outros só abrem o Chrome).
COMANDOS_COM_CHROME = ("ne_processar", "ne_lote")


class _Estado:
    def __init__(self):
        self.emitir = lambda tipo, **dados: None
        self.janela = lambda: None
        self.trabalhador = None
        self.esperar_resposta = lambda: ""
        self.responder = lambda texto: None
        self.ler_config = dict
        self.gravar_config = lambda **valores: None
        # A última lista lida (planilha ou texto colado) e de onde veio.
        self.itens: list[lote.ItemNE] = []
        self.fonte = ("texto", "")


_e = _Estado()


def configurar(emitir, janela, trabalhador, esperar_resposta, responder, ler_config, gravar_config) -> None:
    """Chamado uma vez pelo app_janela, na primeira vez que a página fala com a NE."""
    _e.emitir, _e.janela, _e.trabalhador = emitir, janela, trabalhador
    _e.esperar_resposta, _e.responder = esperar_resposta, responder
    _e.ler_config, _e.gravar_config = ler_config, gravar_config


# ================================================== a página -> o Python


def _item_para_tela(item) -> dict:
    return {
        "linha": item.linha, "processo": item.processo, "ne": item.ne, "erro": item.erro,
        "ja_concluida": item.ja_concluida, "original": item.original,
    }


def _ne_para_tela(texto: str):
    ne = etapa.normalizar_ne(texto or "")
    return {"ne": ne, "completa": f"{etapa.ANO_SIGEF}NE{ne}"} if ne else None


def _estado() -> dict:
    sessao = carregar_sessao()
    return {
        "ok": True, "versao": __version__, "pasta": PASTA_BASE, "ano": etapa.ANO_SIGEF, "tipo_sei": etapa.TEXTO_LINK_NE,
        "processo": sessao.get("processo") or "", "ne": sessao.get("ne") or "",
    }


def _validar(d: dict) -> dict:
    return {"ok": True, "processo": normalizar_processo_sei(d.get("processo") or "") or None,
            "ne": _ne_para_tela(d.get("ne"))}


def _processar(d: dict) -> dict:
    processo = normalizar_processo_sei(d.get("processo") or "")
    if not processo:
        return {"ok": False, "campo": "processo"}
    ne = _ne_para_tela(d.get("ne"))
    if not ne:
        return {"ok": False, "campo": "ne"}
    nome_arvore = (d.get("nome_arvore") or "").strip()[:50]  # 50: o limite do campo no SEI
    _e.trabalhador.comandos.put(("ne_processar", {"processo": processo, "ne": ne["ne"], "nome_arvore": nome_arvore}))
    return {"ok": True, "processo": processo, "ne": ne["ne"], "ne_completa": ne["completa"]}


def _ler() -> dict:
    origem, valor = _e.fonte
    try:
        _e.itens = lote.ler_arquivo_ne(valor) if origem == "arquivo" else lote.ler_texto_ne(valor)
    except Exception as erro:  # planilha corrompida, .xls antigo, arquivo aberto em outro programa
        _e.itens = []
        return {"ok": False, "erro": str(erro) or type(erro).__name__, "arquivo": valor if origem == "arquivo" else ""}
    return {
        "ok": True,
        "arquivo": os.path.basename(valor) if origem == "arquivo" else "",
        "itens": [_item_para_tela(item) for item in _e.itens],
    }


def _ler_texto(d: dict) -> dict:
    _e.fonte = ("texto", d.get("texto") or "")
    return _ler()


def _escolher_planilha() -> dict:
    import webview

    escolhido = _e.janela().create_file_dialog(
        webview.FileDialog.OPEN,
        file_types=("Planilhas e listas (*.xlsx;*.csv;*.txt)", "Todos os arquivos (*.*)"),
    )
    if not escolhido:
        return {"ok": False, "cancelou": True}
    _e.fonte = ("arquivo", escolhido[0])
    return _ler()


def _processar_lote(d: dict) -> dict:
    """Roda a última lista lida; `linhas` refaz só essas (as que deram erro)."""
    itens = [item for item in _e.itens if item.valido]
    if d.get("linhas"):
        linhas = set(d["linhas"])
        itens = [item for item in itens if item.linha in linhas]
    # NE já anexada antes não é pulada (vai de novo, com aviso): só atualiza a marca.
    for item in itens:
        item.ja_concluida = etapa.ne_ja_concluida(item.processo, item.ne)
    if not itens:
        return {"ok": False, "erro": "A lista não tem nenhuma linha válida."}
    _e.trabalhador.parar_lote.clear()
    _e.trabalhador.comandos.put(("ne_lote", {"itens": itens}))
    return {"ok": True, "quantidade": len(itens)}


def _opcoes_relatorio() -> dict:
    hoje = date.today()
    return {"ok": True, "de": hoje.replace(day=1).isoformat(), "ate": hoje.isoformat(),
            "minutos_manual": _e.ler_config().get("minutos_manual_por_ne", 15)}


def _relatorio(d: dict) -> dict:
    try:
        minutos = float(str(d.get("minutos_manual")).replace(",", "."))
        if minutos <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Informe quantos minutos leva uma NE feita à mão (ex.: 15)."}
    try:
        inicio, fim = date.fromisoformat(d.get("de") or ""), date.fromisoformat(d.get("ate") or "")
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Confira as datas do período."}
    _e.gravar_config(minutos_manual_por_ne=minutos)
    try:
        caminho = relatorio.gerar(inicio, fim, minutos)
    except Exception as erro:  # planilha de métricas travada/corrompida
        return {"ok": False, "erro": f"Não consegui montar o relatório: {erro}"}
    os.startfile(caminho)
    return {"ok": True, "caminho": caminho}


def _abrir(caminho: str, pasta: bool) -> dict:
    alvo = caminho if caminho and (os.path.isdir(caminho) if pasta else pode_abrir(caminho)) else ""
    if pasta and not alvo:
        alvo = PASTA_BASE
    if alvo:
        os.startfile(alvo)
    return {"ok": bool(alvo)}


def chamar(acao: str, dados: dict | None = None) -> dict:
    """A porta única da página da NE (ne.js)."""
    d = dados or {}
    acoes = {
        "estado": _estado,
        "validar": lambda: _validar(d),
        "conectar": lambda: _e.trabalhador.comandos.put(("ne_conectar", {})) or {"ok": True},
        "login_ok": lambda: _e.trabalhador.comandos.put(("ne_apos_login", {})) or {"ok": True},
        "processar": lambda: _processar(d),
        "ler_texto": lambda: _ler_texto(d),
        "escolher_planilha": _escolher_planilha,
        "processar_lote": lambda: _processar_lote(d),
        "parar_lote": lambda: _e.trabalhador.parar_lote.set() or {"ok": True},
        "concluir_conferencia": lambda: _e.responder("") or {"ok": True},
        "opcoes_relatorio": _opcoes_relatorio,
        "relatorio": lambda: _relatorio(d),
        "abrir_pasta": lambda: _abrir(d.get("caminho") or "", pasta=True),
        "abrir_arquivo": lambda: _abrir(d.get("caminho") or "", pasta=False),
    }
    if acao not in acoes:
        return {"ok": False, "erro": f"Ação desconhecida: {acao}"}
    return acoes[acao]()


# ===================================== o Trabalhador (thread do Chrome)


def _resumo(dados: dict) -> dict:
    arquivos = []
    for caminho in dados.get("arquivos") or []:
        try:
            kb = round(os.path.getsize(caminho) / 1024)
        except OSError:
            kb = 0
        arquivos.append({"nome": os.path.basename(caminho), "kb": kb})
    return {"ne": dados.get("ne"), "pasta": dados.get("pasta_processo"), "arquivos": arquivos,
            "avisos": list(dados.get("avisos_download") or [])}


def _conectar(t) -> None:
    t._conectar()
    _e.emitir("ne_conectado")


def _apos_login(t) -> None:
    """O usuário confirmou o login: a aba do SIGEF vai para a tela 'Imprimir Nota de Empenho'."""
    t._garantir_conexao()
    print("🔁 Levando a aba do SIGEF para a tela da Nota de Empenho...")
    try:
        t.aba_sigef.goto(etapa.URL_SIGEF_NE, timeout=60000)
    except Exception:
        pass  # baixar_ne confere a sessão de novo antes de usar
    _garantir_url_certa(t.aba_sigef, DOMINIO_SIGEF, etapa.URL_SIGEF_NE, "SIGEF")


def _processar_uma(t, processo: str, ne: str, nome_arvore: str = "") -> None:
    t._garantir_conexao()

    def ao_etapa(nome, dados=None):
        _e.emitir("ne_etapa", etapa=nome)
        if dados:
            _e.emitir("ne_resumo", resumo=_resumo(dados))

    # O relógio da NE para dentro de processar_ne, antes da conferência.
    t.aba_sigef, avisos, tempos = etapa.processar_ne(
        t.context, t.aba_sigef, processo, ne, ao_etapa=ao_etapa, nome_arvore=nome_arvore
    )
    _e.emitir("ne_conferencia", processo=processo, avisos=avisos)
    _e.esperar_resposta()  # a pessoa confere no SEI e clica em "Concluí a conferência"
    _e.emitir("ne_concluido", processo=processo, ne=ne, tempos=tempos)


def _processar_lote_no_chrome(t, itens: list) -> None:
    t._garantir_conexao()
    validos = [item for item in itens if item.valido]
    _e.emitir("ne_lote_inicio", itens=[_item_para_tela(item) for item in validos])
    comecados = set()  # uma NE tentada de novo depois de uma queda não reinicia a tela

    def ao_etapa(indice, nome, resultados):
        if nome == "fim":
            r = resultados[indice]
            _e.emitir("ne_lote_item", indice=indice, estado=r.estado, mensagem=r.mensagem,
                      avisos=r.avisos, pasta=r.pasta, tempo=r.tempo)
            return
        if indice not in comecados:
            comecados.add(indice)
            _e.emitir("ne_lote_item", indice=indice, estado="rodando")
        _e.emitir("ne_etapa", etapa=nome)

    resultados, caminho = lote.processar_lote_ne(
        t.context, t.aba_sigef, validos, deve_parar=t.parar_lote.is_set, ao_etapa=ao_etapa,
    )
    _e.emitir(
        "ne_lote_fim", relatorio=caminho,
        resultados=[
            {**_item_para_tela(r.item), "estado": r.estado, "mensagem": r.mensagem,
             "avisos": r.avisos, "pasta": r.pasta, "tempo": r.tempo}
            for r in resultados
        ],
    )


_COMANDOS = {
    "ne_conectar": _conectar,
    "ne_apos_login": _apos_login,
    "ne_processar": _processar_uma,
    "ne_lote": _processar_lote_no_chrome,
}


def executar(trabalhador, comando: str, **argumentos) -> None:
    """Um comando "ne_*" do Trabalhador. Os erros sobem para ele, que avisa a página ("ne_erro")."""
    _COMANDOS[comando](trabalhador, **argumentos)
