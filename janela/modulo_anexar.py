"""
O Anexar Documentos (regularização de parcelas: CE, NL e PP de cada lançamento e uma OB no SIGEF,
depois os relatórios baixados e anexados no processo do SEI) dentro da janela.

A automação é a do programa "Anexar Documentos" 1.6, sem mudança de regra, em
automacoes/anexar/. Aqui fica só o que a janela PySide6 dele (anexar/janela/) fazia por cima
do núcleo (automacoes/anexar/aplicativo/nucleo.py), agora respondendo à página da Central
(janela/interface/anexar.js), com as mesmas telas:

    Início · Fazer um processo (ao vivo) · Configurações · Estatísticas · Relatório do mês ·
    Ajuda e licença, e o Modo treino

Como no programa original, a automação roda em OUTRO processo (o executor, que a Central abre
como  python -m automacoes.anexar.aplicativo.executor  ou, instalada, como  <exe> --executor):
cada pergunta chega como um PEDIDO (botões, a tabela dos dados, "Confira os dados",
configurações) que a página desenha; a resposta é o botão clicado. A página lê o que aconteceu
pela porta "novidades" (a cada fração de segundo), como a janela original lia o núcleo.

A página chama tudo por UMA porta, chamar(acao, dados) (Api.anexar do app_janela).

O QUE MUDA POR ESTAR NA CENTRAL (de propósito, como no DARE):
    - um Chrome só e o ano do SIGEF: ver automacoes/anexar/central.py;
    - uma automação por vez: o processo de verdade só começa com o USO_DO_CHROME de
      modulos_janela, que fica com ele até o executor terminar (o Modo treino não usa o Chrome);
    - a pasta dados/ fica em Documentos\\Anexar Documentos, fora da pasta do programa. Na primeira
      vez, o que o Anexar Documentos instalado já tinha (configurações, sessão, relatórios) é copiado
      para lá, sem apagar o original.
    - tamanho da letra (A / A+ / A++), aviso sonoro e as escolhas das telas são lembrados pela
      própria página; o claro/escuro segue o da Central.
"""
import os
import shutil
import threading
import time
import traceback

# Antes de importar o Anexar: a pasta dados/ (sessão, configurações, relatórios) fora da pasta do programa.
from automacoes.geral import PASTA_DADOS_ANEXAR  # noqa: E402

PASTA_DADOS = os.environ.setdefault("ANEXAR_PASTA_DADOS", PASTA_DADOS_ANEXAR)
PASTA_DADOS_ANTIGA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Anexar Documentos", "dados")


def _trazer_dados_antigos(origem: str = PASTA_DADOS_ANTIGA, destino: str = PASTA_DADOS) -> bool:
    """Copia a pasta dados/ do Anexar Documentos instalado, se a da Central ainda não existe."""
    if not origem or not os.path.isdir(origem) or os.path.exists(destino):
        return False
    try:
        shutil.copytree(origem, destino)
        return True
    except OSError:
        return False


_trazer_dados_antigos()

from automacoes.anexar import caminhos  # noqa: E402
from automacoes.anexar.aplicativo import estatisticas as contas  # noqa: E402
from automacoes.anexar.aplicativo import metricas, nucleo  # noqa: E402
from automacoes.anexar.automacao import configuracoes  # noqa: E402
from automacoes.anexar.automacao.utils import PASTA_BASE as PASTA_PROCESSOS  # noqa: E402
from automacoes.anexar.sistema import ambiente  # noqa: E402
from automacoes.anexar.versao import AUTOR, DATA_VERSAO, NOME_APLICATIVO, VERSAO  # noqa: E402
from janela import modulos_janela  # noqa: E402


class _Estado:
    def __init__(self):
        self.janela = lambda: None
        self.execucao = nucleo.Execucao()
        self.trava_chrome = False


_e = _Estado()


def configurar(janela) -> None:
    """Chamado uma vez pelo app_janela: como achar a janela (caixas de abrir/salvar arquivo)."""
    _e.janela = janela


def executando() -> bool:
    return _e.execucao.rodando


def encerrar() -> None:
    """A janela fechou com a automação rodando: pede para parar (ela guarda tudo o que já fez)."""
    if _e.execucao.rodando:
        _e.execucao.parar()
        limite = time.time() + 8
        while _e.execucao.rodando and time.time() < limite:
            time.sleep(0.1)


# ============================================================ Fazer um processo


def _soltar_o_chrome_no_fim(processo) -> None:
    """O USO_DO_CHROME fica com o Anexar até o executor terminar (ele mesmo usa o Chrome)."""
    def esperar():
        try:
            processo.wait()
        finally:
            if _e.trava_chrome:
                _e.trava_chrome = False
                modulos_janela.USO_DO_CHROME.release()

    threading.Thread(target=esperar, daemon=True, name="anexar-fim").start()


def _iniciar(treino: bool) -> dict:
    if _e.execucao.rodando:
        return {"ok": False, "erro": "O programa já está rodando. Termine ou pare antes de começar outro."}
    if not treino:
        if not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
            return {"ok": False, "erro": "Outra automação está usando o Chrome agora. Espere ela terminar e "
                                         "tente de novo (o Modo treino não usa o Chrome)."}
        _e.trava_chrome = True
    try:
        _e.execucao.iniciar("automacao", treino=treino)
    except (RuntimeError, OSError) as erro:
        if _e.trava_chrome:
            _e.trava_chrome = False
            modulos_janela.USO_DO_CHROME.release()
        return {"ok": False, "erro": str(erro)}
    if _e.trava_chrome:
        _soltar_o_chrome_no_fim(_e.execucao.processo)
    return {"ok": True, "treino": bool(treino)}


def _novidades(seq) -> dict:
    try:
        seq = int(seq or 0)
    except (TypeError, ValueError):
        seq = 0
    return {"ok": True, "itens": _e.execucao.itens_desde(seq), "estado": _e.execucao.estado()}


def _responder(resposta, id_pergunta) -> dict:
    try:
        _e.execucao.responder(resposta, id_pergunta)
    except (RuntimeError, OSError) as erro:
        return {"ok": False, "erro": str(erro), "estado": _e.execucao.estado()}
    return {"ok": True}


# ============================================================ Início e Ajuda


def _estado() -> dict:
    try:
        diagnostico = ambiente.diagnostico()
    except Exception:  # noqa: BLE001 - a verificação nunca derruba a tela
        diagnostico = {"problemas": []}
    return {
        "ok": True, "nome": NOME_APLICATIVO, "versao": VERSAO, "data_versao": DATA_VERSAO, "autor": AUTOR,
        "retomar": nucleo.resumo_da_sessao(), "problemas": diagnostico.get("problemas") or [],
        "execucao": _e.execucao.estado(), "pasta_dados": caminhos.PASTA_DADOS, "pasta_processos": PASTA_PROCESSOS,
    }


def _ambiente() -> dict:
    try:
        info = ambiente.diagnostico()
    except Exception as erro:  # noqa: BLE001
        return {"ok": False, "erro": f"Não foi possível verificar: {erro}"}
    linhas = [{"ok": bool(info["chrome"]), "nome": "Google Chrome", "valor": info["chrome"] or "Não encontrado"}]
    for nome, versao in info["bibliotecas"].items():
        linhas.append({"ok": bool(versao), "nome": info["nomes_bibliotecas"].get(nome, nome),
                       "valor": f"versão {versao}" if versao else "Não instalada"})
    linhas.append({"ok": info["pasta_gravavel"], "nome": "Pasta do programa",
                   "valor": info["pasta_programa"] + ("" if info["pasta_gravavel"] else " (não deixa gravar)")})
    linhas.append({"ok": True, "nome": "Pasta dos dados", "valor": caminhos.PASTA_DADOS})
    linhas.append({"ok": True, "nome": "Python",
                   "valor": f"{info['python']}{' (vem junto com o programa)' if info['congelado'] else ''}"})
    linhas.append({"ok": True, "nome": "Perfil do Chrome do programa", "valor": info["perfil_chrome"]})
    return {"ok": True, "linhas": linhas, "problemas": info.get("problemas") or []}


def _ajuda() -> dict:
    return {"ok": True, "licenca": nucleo.ler_licenca(), "versao": VERSAO, "data_versao": DATA_VERSAO,
            "autor": AUTOR, **_ambiente()}


PASTAS = {"relatorios": lambda: metricas.PASTA_RELATORIOS, "programa": lambda: nucleo.PASTA_PROJETO,
          "dados": lambda: caminhos.PASTA_DADOS, "processos": lambda: PASTA_PROCESSOS}


def _abrir_pasta(qual: str) -> dict:
    if qual not in PASTAS:
        return {"ok": False, "erro": "pasta desconhecida"}
    try:
        nucleo.abrir_no_explorador(PASTAS[qual]())
    except OSError as erro:
        return {"ok": False, "erro": str(erro)}
    return {"ok": True}


# ============================================================ Configurações


def _config_salvar(secao: str, valores: dict = None, padrao: bool = False) -> dict:
    try:
        nova = nucleo.salvar_configuracao(_e.execucao, secao, valores, padrao=padrao)
    except configuracoes.ErroNasConfiguracoes as erro:
        return {"ok": False, "erros": erro.erros, "erro": "Algum valor não pôde ser salvo: veja em vermelho."}
    except RuntimeError as erro:
        return {"ok": False, "erro": str(erro)}
    return {"ok": True, "secao": nova}


# ============================================================ Estatísticas e Relatório do mês


def _dados():
    return metricas.ler_execucoes(), metricas.ler_estimativas()


def _estatisticas(periodo: str, quantidade) -> dict:
    execucoes, estimativas = _dados()
    do_periodo = contas.no_periodo(execucoes, periodo or "tudo")
    conta = contas.calcular_economia(do_periodo, estimativas)
    return {
        "ok": True, "processos": len(do_periodo), "total": conta["total"], "linhas": conta["linhas"],
        "estimativas": estimativas, "periodos": contas.PERIODOS,
        "categorias": [{**c, "curto": contas.NOME_CURTO_CATEGORIA.get(c["chave"], c["chave"])}
                       for c in metricas.CATEGORIAS],
        "maximo": metricas.ESTIMATIVA_MAXIMA, "projecao": _projecao(do_periodo, estimativas, quantidade),
    }


def _projecao(do_periodo, estimativas, quantidade):
    try:
        quantidade = max(1, min(100000, int(float(str(quantidade or 100).replace(",", ".")))))
    except ValueError:
        quantidade = 100
    return contas.projecao(do_periodo, estimativas, quantidade)


def _salvar_estimativas(valores: dict) -> dict:
    try:
        return {"ok": True, "estimativas": metricas.salvar_estimativas(valores or {})}
    except (ValueError, OSError) as erro:
        return {"ok": False, "erro": str(erro)}


def _relatorio(mes: str) -> dict:
    from datetime import datetime

    execucoes, _ = _dados()
    meses = contas.meses_disponiveis(execucoes)
    mes = mes if mes in meses else contas.chave_mes(datetime.now())
    do_mes = contas.execucoes_do_mes(execucoes, mes)
    processos = []
    for e in sorted(do_mes, key=lambda e: str(e.get("inicio")), reverse=True):
        data = contas.data_de(e)
        texto, tom = contas.SITUACAO.get(e.get("situacao"), contas.SITUACAO["pendente"])
        processos.append({
            "data": data.strftime("%d/%m/%Y") if data else "—", "hora": data.strftime("%H:%M") if data else "",
            "processo": e.get("processo") or "—",
            "lancamentos": e.get("lancamentos") if e.get("lancamentos") is not None else "—",
            "duracao_s": e.get("duracao_s"), "humano_s": e.get("humano_s"), "situacao": texto, "tom": tom,
            "erros": "; ".join(x.get("titulo") or "" for x in e.get("erros") or []),
        })
    return {"ok": True, "mes": mes, "meses": [{"chave": m, "nome": contas.nome_mes(m)} for m in meses],
            "nome_mes": contas.nome_mes(mes), "detalhe": contas.detalhe_do_mes(do_mes), "processos": processos}


def _exportar(d: dict) -> dict:
    """As planilhas do estudo e a do mês: a pessoa escolhe onde salvar (como na janela original)."""
    import webview

    execucoes, estimativas = _dados()
    do_periodo = contas.no_periodo(execucoes, d.get("periodo") or "tudo")
    anonimo = bool(d.get("anonimo", True))
    hoje = time.strftime("%Y-%m-%d")
    tipo = d.get("tipo")
    if tipo == "processos":
        nome, conteudo = f"anexar_processos_{hoje}.csv", contas.planilha_processos(do_periodo, anonimo)
    elif tipo == "etapas":
        nome, conteudo = f"anexar_etapas_{hoje}.csv", contas.planilha_etapas(do_periodo, anonimo)
    elif tipo == "economia":
        nome, conteudo = f"anexar_economia_{hoje}.csv", contas.planilha_economia(do_periodo, estimativas)
    elif tipo == "json":
        nome = f"anexar_dados_{hoje}.json"
        conteudo = contas.dados_completos(do_periodo, estimativas, d.get("periodo") or "tudo", anonimo)
    elif tipo == "mes":
        mes = str(d.get("mes") or "")
        nome, conteudo = f"anexar_relatorio_{mes}.csv", contas.planilha_do_mes(contas.execucoes_do_mes(execucoes, mes), mes)
    else:
        return {"ok": False, "erro": "planilha desconhecida"}
    pasta = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(pasta):
        pasta = os.path.expanduser("~")
    escolhido = _e.janela().create_file_dialog(webview.FileDialog.SAVE, directory=pasta, save_filename=nome)
    if not escolhido:
        return {"ok": False, "cancelou": True}
    caminho = escolhido[0] if isinstance(escolhido, (list, tuple)) else escolhido
    try:
        with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
            arquivo.write(conteudo)
    except OSError as erro:
        return {"ok": False, "erro": f"Não foi possível salvar: {erro}"}
    return {"ok": True, "texto": f"Arquivo “{os.path.basename(caminho)}” salvo."}


# ============================================================ porta

_ACOES = {
    "estado": lambda d: _estado(),
    "iniciar": lambda d: _iniciar(bool(d.get("treino"))),
    "novidades": lambda d: _novidades(d.get("seq")),
    "responder": lambda d: _responder(d.get("resposta"), d.get("id")),
    "parar": lambda d: (_e.execucao.parar(), {"ok": True})[1],
    "config_tabelas": lambda d: {"ok": True, **nucleo.tabelas_de_configuracao(_e.execucao)},
    "config_salvar": lambda d: _config_salvar(d.get("secao", ""), d.get("valores") or {}),
    "config_padrao": lambda d: _config_salvar(d.get("secao", ""), padrao=True),
    "estatisticas": lambda d: _estatisticas(d.get("periodo"), d.get("quantidade")),
    "salvar_estimativas": lambda d: _salvar_estimativas(d.get("valores")),
    "relatorio": lambda d: _relatorio(d.get("mes") or ""),
    "exportar": _exportar,
    "ajuda": lambda d: _ajuda(),
    "ambiente": lambda d: _ambiente(),
    "abrir_pasta": lambda d: _abrir_pasta(d.get("qual", "")),
}


def chamar(acao: str, dados: dict | None = None) -> dict:
    """A porta única da página do Anexar Documentos: chamar("iniciar", {...}) etc."""
    funcao = _ACOES.get(acao)
    if funcao is None:
        return {"ok": False, "erro": f"ação desconhecida: {acao}"}
    try:
        return funcao(dados or {})
    except Exception as falha:  # noqa: BLE001 - a página sempre recebe uma resposta
        print(traceback.format_exc())
        return {"ok": False, "erro": str(falha) or type(falha).__name__}
