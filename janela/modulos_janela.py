"""
O outro programa dentro da janela: Automações BB (carga de cartões no
portal do Banco do Brasil).

A lógica dele continua no seu arquivo, sem mudança de regra:

    automacoes/bb/automacoes_bb.py  (era o núcleo do AutomacoesBB)

Aqui fica só a ligação com a janela: ler/gravar a configuração e rodar
a automação escolhida numa thread própria. O que ele imprime já cai no
registro da janela (app_janela troca o sys.stdout), e o input() dele
vira a caixa de pergunta da janela.

UMA AUTOMAÇÃO POR VEZ: os dois módulos (SIGEF → SEI e BB) usam o mesmo
Chrome da automação. USO_DO_CHROME garante que nunca rodam juntos.
"""
import os
import threading
import traceback

# Antes de importar os módulos: pastas de dados e saída sem cores ANSI.
# O BB usa a MESMA pasta do programa BB instalado (Documentos\Automacoes
# BB), para reaproveitar a configuração e os PDFs que já existem.
os.environ.setdefault("BB_PASTA_DADOS", os.path.join(os.path.expanduser("~"), "Documents", "Automacoes BB"))
os.environ.setdefault("BB_SEM_COR", "1")

USO_DO_CHROME = threading.Lock()


def _bb():
    from automacoes.bb import automacoes_bb as bb
    bb.limpar_tela = lambda: None   # sem terminal: o registro é contínuo
    return bb


# ------------------------------------------------------------- execução


def rodar(modulo: str, rotulo: str, funcao, emitir) -> dict:
    """
    Roda `funcao()` numa thread nova, com o COM (Excel) iniciado nela.
    Avisa a janela com os eventos "modulo_inicio" e "modulo_fim".
    """
    if not USO_DO_CHROME.acquire(blocking=False):
        return {"ok": False, "erro": "Já tem uma automação rodando. Espere ela terminar (ou peça para parar)."}

    def corpo():
        erro = None
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pythoncom = None
        try:
            funcao()
        except SystemExit as parada:
            erro = str(parada.code or "").strip() or None
        except BaseException as falha:  # noqa: BLE001 -- nada pode escapar da thread
            if type(falha).__name__ == "Encerrado":   # janela fechada no meio de uma pergunta
                erro = "Janela fechada."
            else:
                erro = str(falha) or type(falha).__name__
                print(traceback.format_exc())
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
            USO_DO_CHROME.release()
            print(f"===== fim: {rotulo}{' (com erro)' if erro else ''} =====")
            emitir("modulo_fim", modulo=modulo, erro=erro)

    print(f"\n===== {rotulo} =====")
    emitir("modulo_inicio", modulo=modulo, nome=rotulo)
    threading.Thread(target=corpo, daemon=True, name=f"modulo-{modulo}").start()
    return {"ok": True}


def parar() -> None:
    """Parar depois da linha em andamento (BB: automacoes_bb.PEDIDO_PARADA)."""
    try:
        _bb().PEDIDO_PARADA.set()
    except Exception:
        pass
    # Se o BB estiver esperando uma resposta na tela, "Parar" cancela ela.
    try:
        bb_responder(_CANCELAR_BB)
    except NameError:
        pass
    print("⏹️  Parada pedida: a linha em andamento termina e a automação para.")


# ------------------------------------------------------------ planilhas


def abas_da_planilha(caminho: str) -> list[str]:
    """Nomes das abas (.xlsx/.xlsm) -- vazio se não der para ler."""
    if not caminho or not os.path.exists(caminho):
        return []
    try:
        return list(_bb().listar_abas(caminho) or [])
    except Exception:
        pass
    try:
        import openpyxl
        livro = openpyxl.load_workbook(caminho, read_only=True)
        try:
            return list(livro.sheetnames)
        finally:
            livro.close()
    except Exception:
        return []


# ------------------------------------------------------------------- BB
#
# O BB foi feito para o terminal: pergunta programa, modo, processo,
# cartão, valor e confirmações no meio da rodada. Na janela essas
# respostas vêm do FORMULÁRIO da tela (preenchido antes de Executar):
#
#   - escolher_programa_carga / escolher_modo_carga / perguntar_campo são
#     trocadas por versões que leem o formulário;
#   - as confirmações de texto ("Enter para simular", "Digite CARREGAR",
#     "REPETIR", "Anexar os dois saldos?") são respondidas com o que foi
#     marcado/digitado no formulário;
#   - o que não dá para prever (login no BB, aba travada, planilha sem
#     gravar, carga a conferir) vira uma pergunta DENTRO da tela do BB,
#     com botões e campo de texto (evento "bb_pergunta").

import queue as _queue
import re as _re

_respostas_bb: dict = {}
_fila_bb: "_queue.Queue[str]" = _queue.Queue()     # respostas da pergunta na tela
_REGEX_ANSI = _re.compile(r"\x1b\[[0-9;]*m")
_CANCELAR_BB = "\x00cancelar"

# Campos do formulário que cada automação usa (a tela mostra só esses).
_CAMPOS_BB = {
    "executar_carga_limite": ["programa", "modo", "repetidos"],
    "executar_carga_avulsa": ["avulsa", "programa", "modo", "anexar_saldos"],
}


def _limpar(texto: str) -> str:
    return " ".join(_REGEX_ANSI.sub("", str(texto or "")).replace("➜", "").split())


def _opcoes_do_texto(texto: str) -> list[dict]:
    """
    Botões a partir do próprio texto da pergunta do BB, que diz as teclas:
    "Enter para verificar de novo · 'f' para FECHAR essa(s) aba(s) · 'c' para cancelar"
    """
    opcoes = []
    texto = texto.replace("(s)", "s")          # "essa(s) aba(s)" -> "essas abas"
    achado = _re.search(r"(?:Enter|tecle Enter)\s*(?:\(Enviar\)\s*)?(?:para\s+([^·(',]+))?", texto, _re.I)
    if achado:
        rotulo = (achado.group(1) or "continuar").strip(" ,.")
        opcoes.append({"valor": "", "rotulo": rotulo[:1].upper() + rotulo[1:]})
    for tecla, rotulo in _re.findall(r"'(\w)'\s+para\s+([^·()',]+)", texto):
        opcoes.append({"valor": tecla, "rotulo": rotulo.strip(" ,.").capitalize()})
    if not opcoes and _re.search(r"\(s/N\)", texto, _re.I):
        opcoes = [{"valor": "s", "rotulo": "Sim"}, {"valor": "n", "rotulo": "Não"}]
    return opcoes


def _perguntar_na_tela(texto: str) -> str:
    """Pergunta que o formulário não cobre: aparece na tela do BB e espera."""
    while not _fila_bb.empty():          # sobra de uma pergunta anterior
        _fila_bb.get_nowait()
    _emitir_bb("bb_pergunta", texto=texto, opcoes=_opcoes_do_texto(texto))
    resposta = _fila_bb.get()
    _emitir_bb("bb_pergunta_fim")
    return resposta


def _perguntar_bb(texto) -> str:
    """No lugar de automacoes_bb.perguntar."""
    limpo = _limpar(texto)
    r = _respostas_bb
    baixo = limpo.lower()
    bb = _bb()
    if "enter para simular" in baixo:
        return ""
    if f"digite {bb.PALAVRA_CONFIRMACAO.lower()}" in baixo:
        return r.get("confirmacao", "")
    if "nova parcela" in baixo and "repetir" in baixo:
        return "REPETIR" if r.get("nova_parcela") else ""
    if "anexar os dois saldos no sei" in baixo:
        return "s" if r.get("anexar_saldos") else "n"
    if baixo.startswith("enter para anexar em"):
        return ""
    print(f"  ❓ {limpo}  (responda na tela do Banco do Brasil)")
    resposta = _perguntar_na_tela(limpo)
    print(f"     resposta: {'(cancelado)' if resposta == _CANCELAR_BB else (resposta or 'Enter')}")
    return resposta


def _escolher_programa_bb() -> bool:
    bb = _bb()
    programa = _respostas_bb.get("programa")
    if programa not in bb.PROGRAMAS_CARGA:
        bb.msg_erro("Escolha o programa (PNAE ou PROAFI) na tela.")
        return False
    bb.PROGRAMA_CARGA = programa
    bb.msg_ok(f"Programa: {programa}")
    return True


def _escolher_modo_bb():
    modo = _respostas_bb.get("modo")
    if modo not in ("simulacao", "real"):
        return None
    _bb().msg_ok("Modo: SIMULAÇÃO (não confirma nada)" if modo == "simulacao" else "Modo: REAL")
    return modo == "simulacao"


def _perguntar_campo_bb(rotulo, converter):
    """Processo, cartão e valor da Carga Avulsa, vindos do formulário."""
    chave = next((k for k in ("processo", "cartao", "valor") if rotulo.lower().startswith(
        {"processo": "processo", "cartao": "número do cartão", "valor": "valor"}[k])), None)
    if chave is None:
        return _bb().__dict__["_perguntar_campo_original"](rotulo, converter)
    try:
        return converter(str(_respostas_bb.get(chave, "")).strip())
    except ValueError as erro:
        raise SystemExit(f"{rotulo.rstrip(':')} — {erro}")


def _resolver_repetidos_bb(linhas):
    """Cartões repetidos na planilha: responde o menu com a escolha da tela."""
    bb = _bb()
    escolha = _respostas_bb.get("repetidos", "primeira")
    respostas = iter(["2", "REPETIR"] if escolha == "todas" else ["1"])
    anterior = bb.perguntar
    bb.perguntar = lambda _texto: next(respostas, "3")
    try:
        return bb.__dict__["_resolver_repetidos_original"](linhas)
    finally:
        bb.perguntar = anterior


_emitir_bb = lambda *a, **k: None   # noqa: E731 -- trocado em bb_executar


def _instalar_respostas_bb(bb) -> None:
    """Troca (uma vez) as perguntas do BB pelas respostas da tela."""
    if bb.__dict__.get("_perguntar_campo_original"):
        return
    bb._perguntar_campo_original = bb.perguntar_campo
    bb._resolver_repetidos_original = bb.resolver_repetidos
    bb.perguntar = _perguntar_bb
    bb.escolher_programa_carga = _escolher_programa_bb
    bb.escolher_modo_carga = _escolher_modo_bb
    bb.perguntar_campo = _perguntar_campo_bb
    bb.resolver_repetidos = _resolver_repetidos_bb


def bb_responder(texto: str) -> None:
    """Resposta da pergunta que apareceu na tela do BB."""
    _fila_bb.put(texto if texto is not None else "")


def _validar_respostas_bb(bb, campos: list, r: dict) -> str | None:
    """Confere o formulário ANTES de começar. Devolve a mensagem de erro, ou None."""
    if "avulsa" in campos:
        for chave, rotulo, converter in (
            ("processo", "Processo", bb._processo_digitado),
            ("cartao", "Cartão", bb._cartao_digitado),
            ("valor", "Valor", bb.valor_inteiro),
        ):
            try:
                converter(str(r.get(chave, "")).strip())
            except ValueError as erro:
                return f"{rotulo}: {erro}"
    if "programa" in campos and r.get("programa") not in bb.PROGRAMAS_CARGA:
        return "Escolha o programa."
    if "modo" in campos:
        if r.get("modo") not in ("simulacao", "real"):
            return "Escolha o modo: simulação ou real."
        if r.get("modo") == "real" and str(r.get("confirmacao", "")).strip().upper() != bb.PALAVRA_CONFIRMACAO:
            return f"Carga REAL: digite {bb.PALAVRA_CONFIRMACAO} no campo de confirmação."
    return None


def _cfg_bb_para_tela(cfg) -> dict:
    return {
        "caminho_planilha": cfg.caminho_planilha,
        "aba_planilha": cfg.aba_planilha,
        "linha_inicial": cfg.linha_inicial,
        "modo_visivel": cfg.modo_visivel,
    }


def bb_estado() -> dict:
    bb = _bb()
    cfg = bb.Configuracao.carregar()
    return {
        "config": _cfg_bb_para_tela(cfg),
        "automacoes": [
            {
                "indice": i, "nome": nome,
                "sem_planilha": bool(getattr(funcao, "sem_planilha", False)),
                "campos": _CAMPOS_BB.get(funcao.__name__, []),
            }
            for i, (nome, funcao) in enumerate(bb.AUTOMACOES)
        ],
        "programas": [
            {"valor": nome, "rotulo": f"{nome} — {dados['filtros']} filtro{'s' if dados['filtros'] > 1 else ''} de carregamento"}
            for nome, dados in bb.PROGRAMAS_CARGA.items()
        ],
        "palavra_confirmacao": bb.PALAVRA_CONFIRMACAO,
        "abas": abas_da_planilha(cfg.caminho_planilha),
        "pasta": bb.PASTA_SCRIPT,
    }


def bb_salvar(valores: dict):
    bb = _bb()
    cfg = bb.Configuracao.carregar()
    cfg.caminho_planilha = (valores.get("caminho_planilha") or "").strip()
    cfg.aba_planilha = (valores.get("aba_planilha") or "").strip()
    try:
        cfg.linha_inicial = max(1, int(valores.get("linha_inicial") or 2))
    except (TypeError, ValueError):
        cfg.linha_inicial = 2
    cfg.modo_visivel = bool(valores.get("modo_visivel", True))
    cfg.salvar()
    return cfg


def bb_executar(valores: dict, indice: int, emitir, respostas: dict | None = None) -> dict:
    global _emitir_bb
    bb = _bb()
    cfg = bb_salvar(valores)
    if not 0 <= indice < len(bb.AUTOMACOES):
        return {"ok": False, "erro": "Escolha uma automação."}
    nome, funcao = bb.AUTOMACOES[indice]
    respostas = dict(respostas or {})
    erro = _validar_respostas_bb(bb, _CAMPOS_BB.get(funcao.__name__, []), respostas)
    if erro:
        return {"ok": False, "erro": erro}
    usa_planilha = not getattr(funcao, "sem_planilha", False)
    if usa_planilha:
        pode, motivo = cfg.pronta_para_executar()
        if not pode:
            # O texto do BB cita o menu do terminal ("opção 1"); aqui é o botão.
            return {"ok": False, "erro": motivo.replace(" (opção 1)", "").replace("(opção 1)", "")}
        if not cfg.aba_planilha:
            return {"ok": False, "erro": "Escolha a aba da planilha."}
    bb.PEDIDO_PARADA.clear()
    _instalar_respostas_bb(bb)
    _respostas_bb.clear()
    _respostas_bb.update(respostas)
    _emitir_bb = emitir
    while not _fila_bb.empty():
        _fila_bb.get_nowait()

    def tarefa():
        try:
            if usa_planilha:
                bb.abrir_planilha_no_excel(cfg)
            if not bb.garantir_chrome_em_debug(cfg):
                raise SystemExit("Sem o Chrome da automação (porta 9222) o BB não roda.")
            funcao(cfg)
        except bb.ErroDeUso as erro:
            raise SystemExit(str(erro))
        finally:
            try:
                cfg.salvar()
            except Exception:
                pass

    return rodar("bb", f"BB · {nome}", tarefa, emitir)
