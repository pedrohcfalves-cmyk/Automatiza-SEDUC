"""
O DARE (gera o DARE avulso, salva o PDF e anexa no SEI) dentro da janela.

O motor e as regras são os do aplicativo DARE, sem mudança, em automacoes/dare/.
Aqui fica só o que a janela Tkinter do DARE (dare_auto/gui/) fazia por cima dele,
agora respondendo à página da Central (janela/interface/dare.js):

    Início          situação geral, últimas execuções
    Lançamentos     formulário com validação, lista, importar planilha
    Execução        motor.executar numa thread, eventos para a tela
    Arquivos PDF    tamanho da pasta, limpeza (Lixeira, protege os não anexados)
    Desempenho      métricas, monitor, diagnóstico, testes de velocidade
    Configurações   versão, navegador, pastas, valores fixos

A página chama tudo por UMA porta, chamar(acao, dados), e recebe os eventos do
motor pela ponte da janela (tipos "dare_*").

UMA AUTOMAÇÃO POR VEZ: o DARE usa o mesmo Chrome (porta 9222) que o SIGEF → SEI
e o BB. A rodada só começa se conseguir o USO_DO_CHROME de modulos_janela.

UM NAVEGADOR SÓ: quando precisa abrir o Chrome, o DARE abre o da Central (perfil
C:\\ChromeAutomacao), e não o perfil próprio do aplicativo DARE. Como as três
automações usam a mesma porta, perfis diferentes se revezariam nela; com um só, os
logins do SIGEF, do SEI, do BB e do DARE ficam todos salvos no mesmo lugar.
"""
import logging
import os
import queue
import shutil
import threading
import time
import traceback
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from automacoes.dare import (
    __data_versao__,
    __version__,
    armazenamento,
    config,
    limpeza,
    logger,
    menu,
    motor,
    navegador,
    planilha,
    planilha_arquivo,
    preferencias,
    utils,
)
from automacoes.dare.modelos import DadosDare, ResultadoLote
from automacoes.sigef_sei.preparar_navegador import PASTA_PERFIL_CHROME_AUTOMACAO
from janela import modulos_janela

log = logging.getLogger("dare.app")

# O Chrome do DARE é o da Central (ver o topo do arquivo). Só o perfil muda: as
# opções com que o DARE abre o Chrome (abas sem congelar em segundo plano) continuam.
config.PERFIL_CHROME = Path(PASTA_PERFIL_CHROME_AUTOMACAO)


# ======================================================== validações
# As MESMAS regras do formulário do aplicativo DARE (gui/paginas/lancamentos.py).

def _documento(nome: str, digitos: int, validador):
    def validar(texto: str) -> str:
        d = utils.somente_digitos(texto)
        if not d:
            raise ValueError("Campo obrigatório.")
        if len(d) != digitos:
            raise ValueError(f"O {nome} deve ter {digitos} dígitos (tem {len(d)}).")
        if not validador(d):
            raise ValueError(f"{nome} inválido: os dígitos verificadores não conferem.")
        return d
    return validar


def _obrigatorio(funcao):
    def validar(texto: str):
        if not texto.strip():
            raise ValueError("Campo obrigatório.")
        return funcao(texto)
    return validar


def _vencimento(texto: str):
    texto = texto.strip()
    if not texto:
        raise ValueError("Campo obrigatório.")
    d = utils.somente_digitos(texto)
    if len(d) == 8 and "/" not in texto:
        texto = f"{d[:2]}/{d[2:4]}/{d[4:]}"
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Data inválida. Use DD/MM/AAAA (ex.: 10/11/2026).")


def _valor(texto: str) -> str:
    if not texto.strip():
        raise ValueError("Campo obrigatório.")
    try:
        return utils.formatar_valor(texto)
    except ValueError as exc:
        raise ValueError(str(exc).replace("Exemplo", "Ex.")) from exc


# campo da tela -> (validar, exibir)
CAMPOS = {
    "processo": (_obrigatorio(utils.validar_processo), None),
    "cpf": (_documento("CPF", 11, utils.validar_cpf), utils.formatar_cpf),
    "cnpj": (_documento("CNPJ", 14, utils.validar_cnpj), utils.formatar_cnpj),
    "recolhedor": (_documento("CNPJ", 14, utils.validar_cnpj), utils.formatar_cnpj),
    "ref": (_obrigatorio(utils.validar_mes_ano), utils.formatar_mes_ano),
    "venc": (_vencimento, lambda d: d.strftime("%d/%m/%Y")),
    "valor": (_valor, None),
}
ORDEM_CAMPOS = ["processo", "cpf", "cnpj", "recolhedor", "ref", "venc", "valor"]


def _exibir(campo: str, valor) -> str:
    exibir = CAMPOS[campo][1]
    if valor in (None, ""):
        return ""
    return exibir(valor) if exibir else str(valor)


# ============================================================ estado

class _Estado:
    def __init__(self):
        self.lotes: list[DadosDare] = []
        self.executando = False
        self.controle = motor.Controle()
        self.pref = preferencias.Preferencias()
        self.iniciado = False
        self.mensagens_inicio: list[dict] = []
        self.emitir = lambda tipo, **dados: None
        self.janela = lambda: None
        self.trava_chrome = False
        self.monitor = threading.Event()


_e = _Estado()


class _LogParaJanela(logging.Handler):
    """As mensagens INFO+ do DARE vão para o registro da página Execução."""

    def __init__(self):
        super().__init__(level=logging.INFO)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("dare.app", "dare.desempenho")):
            return
        try:
            msg = record.getMessage().splitlines()[0][:400]
        except Exception:  # noqa: BLE001
            return
        nivel = ("erro" if record.levelno >= logging.ERROR else
                 "aviso" if record.levelno >= logging.WARNING else
                 "destaque" if msg.startswith("===") else "")
        _e.emitir("dare_log", hora=time.strftime("%H:%M:%S", time.localtime(record.created)),
                  texto=msg, nivel=nivel)


def configurar(emitir, janela) -> None:
    """Chamado uma vez pelo app_janela: como avisar a página e como achar a janela."""
    _e.emitir = emitir
    _e.janela = janela


def _iniciar_uma_vez() -> None:
    """O que o aplicativo DARE fazia ao abrir (_ao_iniciar), na 1ª vez que o módulo é aberto."""
    if _e.iniciado:
        return
    _e.iniciado = True
    logger.configurar(console=False)
    logging.getLogger("dare").addHandler(_LogParaJanela())
    log.info("Módulo DARE aberto na Central (versão %s).", __version__)
    _e.pref = preferencias.carregar()
    preferencias.aplicar(_e.pref)
    pendentes = armazenamento.carregar_lote()
    if pendentes:
        _e.lotes = pendentes
        _e.mensagens_inicio.append({
            "texto": f"{len(pendentes)} lançamento(s) pendente(s) recuperado(s) da última vez.",
            "tipo": "info"})
    if _e.pref.limpeza_automatica:
        threading.Thread(target=_limpeza_automatica, daemon=True, name="dare-limpeza").start()
    # "Abrir o navegador ao iniciar": na Central, ao abrir o módulo DARE (e não ao abrir
    # o programa, para não trocar o navegador de quem só vai usar o SIGEF → SEI).
    if _e.pref.abrir_navegador_ao_iniciar and not navegador.chrome_debug_ativo() and navegador.localizar_chrome():
        motor.abrir_navegador_em_thread(lambda ok: _e.emitir("dare_navegador", ok=ok, silencioso=True))


def _limpeza_automatica() -> None:
    try:
        r = limpeza.limpeza_automatica(_e.pref.limpeza_dias, _e.pref.usar_lixeira,
                                       _e.pref.proteger_nao_anexados)
    except Exception:  # noqa: BLE001
        log.exception("Falha na limpeza automática")
        return
    if r.apagados:
        _e.pref.ultima_limpeza = datetime.now().strftime("%d/%m/%Y %H:%M")
        preferencias.salvar(_e.pref)
        texto = (f"Limpeza automática: {r.apagados} PDF(s) com mais de {_e.pref.limpeza_dias} dias "
                 f"{'enviados para a Lixeira' if r.para_lixeira else 'apagados'} "
                 f"({limpeza.formatar_bytes(r.bytes_liberados)}).")
        _e.emitir("dare_aviso", texto=texto, tipo="info")


def executando() -> bool:
    return _e.executando


# ============================================================ helpers

def _lote_para_tela(d: DadosDare, i: int | None = None) -> dict:
    linha = {
        "processo": d.processo,
        "cpf": utils.formatar_cpf(d.cpf),
        "cnpj": utils.formatar_cnpj(d.cnpj),
        "recolhedor": utils.formatar_cnpj(d.cnpj_recolhedor),
        "ref": utils.formatar_mes_ano(d.mes_ano_referencia),
        "venc": d.vencimento.strftime("%d/%m/%Y"),
        "valor": d.valor,
        "origem": d.origem or "digitado",
    }
    if i is not None:
        linha["n"] = i
    return linha


def _resultado_para_tela(r: ResultadoLote) -> dict:
    return {"sucesso": r.sucesso, "pdf": r.pdf, "servidor": r.servidor, "erro": r.erro,
            "dados": _lote_para_tela(r.dados)}


def _lista() -> dict:
    """A lista de trabalho como a página Lançamentos mostra (avisos e total incluídos)."""
    total_centavos = 0
    for d in _e.lotes:
        try:
            total_centavos += int(d.valor_digitos)
        except ValueError:
            pass
    reais = utils.formatar_valor(f"{total_centavos / 100:.2f}".replace(".", ",")) if total_centavos else "0,00"
    return {
        "linhas": [_lote_para_tela(d, i) for i, d in enumerate(_e.lotes, 1)],
        "avisos": menu._avisos_lotes(_e.lotes),
        "total": f"{len(_e.lotes)} lançamento(s) · total R$ {reais}" if _e.lotes else "",
        "executando": _e.executando,
    }


def _lotes_alterados() -> None:
    """Guarda a lista (não perde o que foi digitado), como o aplicativo DARE."""
    try:
        if _e.lotes:
            armazenamento.salvar_lote(_e.lotes)
        else:
            armazenamento.limpar_lote()
    except OSError:
        log.warning("Não consegui guardar a lista de lançamentos.", exc_info=True)


def _abrir(caminho) -> bool:
    try:
        os.startfile(str(caminho))  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False


def _navegador() -> dict:
    exe = navegador.localizar_chrome()
    aberto = navegador.chrome_debug_ativo(timeout=0.2)
    return {
        "aberto": aberto,
        "encontrado": bool(exe),
        "nome": navegador.nome_navegador(exe) if exe else "",
        "exe": exe or "",
        "perfil": str(navegador.perfil_para(exe) if exe else config.PERFIL_CHROME),
    }


# ============================================================ Início

def _estado() -> dict:
    _iniciar_uma_vez()
    qtd, tam = limpeza.tamanho_pasta()
    historico = armazenamento.ler_historico(limite=500)
    hoje = date.today().strftime("%d/%m/%Y")
    do_dia = [h for h in historico if (h.get("data_hora") or "").startswith(hoje)]
    ok = sum(1 for h in do_dia if h.get("status") == "SUCESSO")
    recentes = []
    for h in historico[:12]:
        quando = h.get("data_hora", "")
        recentes.append({
            "quando": f"{quando[:5]} {quando[11:16]}" if len(quando) >= 16 else quando,
            "status": h.get("status", ""),
            "processo": h.get("processo", ""),
            "servidor": h.get("servidor", "") or utils.formatar_cpf(h.get("cpf", "")),
            "valor": h.get("valor", ""),
        })
    limite = _e.pref.aviso_tamanho_mb
    mensagens, _e.mensagens_inicio = _e.mensagens_inicio, []
    return {
        "ok": True,
        "versao": __version__,
        "data_versao": __data_versao__,
        "navegador": _navegador(),
        "lista": _lista(),
        "hoje": {"ok": ok, "erros": len(do_dia) - ok},
        "pdfs": {"qtd": qtd, "tamanho": limpeza.formatar_bytes(tam),
                 "acima_do_limite": bool(limite and tam > limite * 1024 ** 2), "limite_mb": limite},
        "pasta_pdf": str(config.PASTA_PDF),
        "recentes": recentes,
        "mensagens": mensagens,
        "fixos_texto": (f"Valores fixos: {config.ORGAO.split(' - ')[0]} · receita {config.CODIGO_RECEITA} · "
                        f"UG {config.UNIDADE_GESTORA} / gestão {config.GESTAO} · série SEI {config.SERIE_SEI}"),
    }


# ======================================================= Lançamentos

def _base() -> DadosDare | None:
    return _e.lotes[-1] if _e.lotes else armazenamento.carregar_ultimos()


def _novo() -> dict:
    """Formulário em branco, com CNPJ, recolhedor, referência, vencimento e valor do anterior."""
    base = _base()
    campos = {c: "" for c in ORDEM_CAMPOS}
    if base:
        campos.update(cnpj=_exibir("cnpj", base.cnpj), recolhedor=_exibir("recolhedor", base.cnpj_recolhedor),
                      ref=_exibir("ref", base.mes_ano_referencia), valor=base.valor)
        mesmo = utils.somente_digitos(base.cnpj) == utils.somente_digitos(base.cnpj_recolhedor)
    else:
        campos["valor"] = config.VALOR_PADRAO
        mesmo = True
    venc = _e.lotes[-1].vencimento if _e.lotes else utils.vencimento_padrao()
    campos["venc"] = _exibir("venc", venc)
    return {"campos": campos, "mesmo": mesmo}


def _validar(campo: str, texto: str) -> dict:
    validar, _ = CAMPOS[campo]
    try:
        valor = validar(texto or "")
    except ValueError as exc:
        return {"ok": False, "erro": str(exc)}
    return {"ok": True, "valor": _exibir(campo, valor)}


def _salvar(valores: dict, indice) -> dict:
    if _e.executando:
        return {"ok": False, "erro": "Aguarde o processamento atual terminar."}
    lidos, erros = {}, {}
    for campo in ORDEM_CAMPOS:
        try:
            lidos[campo] = CAMPOS[campo][0](str(valores.get(campo) or "").strip())
        except ValueError as exc:
            erros[campo] = str(exc)
    if erros:
        return {"ok": False, "erros": erros}
    dados = DadosDare(lidos["processo"], lidos["cnpj"], lidos["cpf"], lidos["recolhedor"],
                      lidos["ref"], lidos["venc"], lidos["valor"])
    if indice is not None and 0 <= int(indice) < len(_e.lotes):
        indice = int(indice)
        dados.origem = _e.lotes[indice].origem
        _e.lotes[indice] = dados
        n, msg = indice + 1, f"Lançamento {indice + 1} atualizado."
    else:
        _e.lotes.append(dados)
        n = len(_e.lotes)
        msg = f"Lançamento {n} adicionado. Preencha o próximo."
    _lotes_alterados()
    return {"ok": True, "n": n, "mensagem": msg, "lista": _lista(), "novo": _novo()}


def _editar(indice: int) -> dict:
    if _e.executando or not 0 <= indice < len(_e.lotes):
        return {"ok": False}
    d = _e.lotes[indice]
    return {
        "ok": True,
        "campos": {"processo": d.processo, "cpf": _exibir("cpf", d.cpf), "cnpj": _exibir("cnpj", d.cnpj),
                   "recolhedor": _exibir("recolhedor", d.cnpj_recolhedor),
                   "ref": _exibir("ref", d.mes_ano_referencia), "venc": _exibir("venc", d.vencimento),
                   "valor": d.valor},
        "mesmo": utils.somente_digitos(d.cnpj) == utils.somente_digitos(d.cnpj_recolhedor),
        "titulo": f"Editando o lançamento {indice + 1}" + (f" ({d.origem})" if d.origem else ""),
    }


def _duplicar(indice: int) -> dict:
    if _e.executando or not 0 <= indice < len(_e.lotes):
        return {"ok": False}
    original = _e.lotes[indice]
    copia = DadosDare(**{**original.para_dict(), "vencimento": original.vencimento, "origem": ""})
    _e.lotes.insert(indice + 1, copia)
    _lotes_alterados()
    return {"ok": True, "lista": _lista(), "editar": _editar(indice + 1), "indice": indice + 1}


def _remover(indices: list) -> dict:
    if _e.executando:
        return {"ok": False}
    for i in sorted({int(i) for i in indices if 0 <= int(i) < len(_e.lotes)}, reverse=True):
        del _e.lotes[i]
    _lotes_alterados()
    return {"ok": True, "lista": _lista(), "novo": _novo()}


def _esvaziar() -> dict:
    if _e.executando:
        return {"ok": False}
    _e.lotes.clear()
    _lotes_alterados()
    return {"ok": True, "lista": _lista(), "novo": _novo()}


# ========================================================== Execução

def _emitir_motor(tipo: str, dados: dict) -> None:
    """Eventos do motor (thread dele) -> página, em JSON."""
    saida = dict(dados)
    if "dados" in saida and isinstance(saida["dados"], DadosDare):
        saida["dados"] = _lote_para_tela(saida["dados"])
    if "resultado" in saida and isinstance(saida["resultado"], ResultadoLote):
        saida["resultado"] = _resultado_para_tela(saida["resultado"])
    if "resultados" in saida:
        saida["resultados"] = [_resultado_para_tela(r) for r in saida["resultados"]]
    pendentes = list(dados.get("pendentes") or [])
    if "pendentes" in saida:
        saida["pendentes"] = len(pendentes)
    if tipo == "fim":
        _e.executando = False
        _e.lotes = pendentes
        if _e.trava_chrome:
            _e.trava_chrome = False
            modulos_janela.USO_DO_CHROME.release()
        saida["lista"] = _lista()
    _e.emitir("dare_motor", evento=tipo, **saida)


def _iniciar() -> dict:
    if _e.executando or not _e.lotes:
        return {"ok": False, "erro": "Não há lançamentos na lista." if not _e.lotes else "Já está processando."}
    if not modulos_janela.USO_DO_CHROME.acquire(blocking=False):
        return {"ok": False, "erro": "Outra automação (SIGEF → SEI ou BB) está usando o Chrome agora. "
                                     "Espere ela terminar e tente de novo."}
    _e.trava_chrome = True
    _e.executando = True
    _e.controle = motor.Controle()
    lotes = list(_e.lotes)
    try:
        motor.iniciar_em_thread(lotes, _emitir_motor, _e.controle)
    except Exception:
        _e.executando = False
        _e.trava_chrome = False
        modulos_janela.USO_DO_CHROME.release()
        raise
    return {"ok": True, "lotes": [_lote_para_tela(d, i) for i, d in enumerate(lotes, 1)]}


def _avisos_inicio() -> dict:
    return {"n": len(_e.lotes), "avisos": menu._avisos_lotes(_e.lotes)}


def _abrir_navegador() -> dict:
    if navegador.chrome_debug_ativo():
        return {"ok": True, "ja_aberto": True}
    exe = navegador.localizar_chrome()
    if not exe:
        return {"ok": False, "erro": "Não encontrei o Google Chrome nem o Microsoft Edge neste computador. "
                                     "Instale o Google Chrome (google.com/chrome) e tente de novo."}
    motor.abrir_navegador_em_thread(lambda ok: _e.emitir("dare_navegador", ok=ok))
    return {"ok": True, "nome": navegador.nome_navegador(exe)}


# ====================================================== Arquivos PDF

def _arquivos() -> dict:
    arquivos = limpeza.listar_pdfs()
    r = limpeza.resumo(arquivos)
    mais_antigo = None
    if r["mais_antigo"]:
        mais_antigo = {"data": r["mais_antigo"].strftime("%d/%m/%Y"),
                       "dias": (datetime.now() - r["mais_antigo"]).days}
    return {
        "ok": True,
        "pasta": str(config.PASTA_PDF),
        "qtd": r["quantidade"],
        "tamanho": limpeza.formatar_bytes(r["bytes"]),
        "media": limpeza.formatar_bytes(r["bytes"] / r["quantidade"]) if r["quantidade"] else "—",
        "mais_antigo": mais_antigo,
        "protegidos": r["protegidos"],
        "arquivos": [{"caminho": str(a.caminho), "nome": a.nome,
                      "data": a.modificado.strftime("%d/%m/%Y %H:%M"),
                      "tamanho": limpeza.formatar_bytes(a.tamanho), "bytes": a.tamanho,
                      "protegido": a.protegido} for a in arquivos],
        "pref": asdict(_e.pref),
        "padrao_data": (date.today() - timedelta(days=30)).strftime("%d/%m/%Y"),
    }


def _escolhidos(d: dict):
    """Os PDFs que a escolha da tela apagaria (None = dias/data inválidos)."""
    arquivos = limpeza.listar_pdfs()
    proteger = bool(d.get("proteger", True))
    criterio = d.get("criterio") or "mais_antigos"
    try:
        if criterio == "selecionados":
            marcados = set(d.get("selecionados") or [])
            return [a for a in arquivos if str(a.caminho) in marcados and not (proteger and a.protegido)]
        if criterio == "mais_antigos":
            return limpeza.selecionar(arquivos, "mais_antigos", dias=int(d.get("dias") or 0), proteger=proteger)
        if criterio == "ate_data":
            ate = datetime.strptime(str(d.get("data") or "").strip(), "%d/%m/%Y").date()
            return limpeza.selecionar(arquivos, "ate_data", ate=ate, proteger=proteger)
        return limpeza.selecionar(arquivos, "todos", proteger=proteger)
    except ValueError:
        return None


def _previa(d: dict) -> dict:
    escolhidos = _escolhidos(d)
    if escolhidos is None:
        return {"ok": False, "erro": "Confira o número de dias ou a data (DD/MM/AAAA)."}
    return {"ok": True, "qtd": len(escolhidos),
            "tamanho": limpeza.formatar_bytes(sum(a.tamanho for a in escolhidos)),
            "caminhos": [str(a.caminho) for a in escolhidos]}


def _limpar(d: dict) -> dict:
    escolhidos = _escolhidos(d)
    if not escolhidos:
        return {"ok": False, "erro": "Nenhum PDF se encaixa nessa escolha."}
    r = limpeza.apagar(escolhidos, lixeira=bool(d.get("lixeira", True)))
    _e.pref.ultima_limpeza = datetime.now().strftime("%d/%m/%Y %H:%M")
    preferencias.salvar(_e.pref)
    return {"ok": True, "apagados": r.apagados, "para_lixeira": r.para_lixeira,
            "liberados": limpeza.formatar_bytes(r.bytes_liberados),
            "falhas": [{"nome": n, "motivo": m} for n, m in r.falhas]}


def _salvar_pref(d: dict) -> dict:
    pref = _e.pref
    for nome in ("usar_lixeira", "proteger_nao_anexados", "limpeza_automatica", "abrir_navegador_ao_iniciar"):
        if nome in d:
            setattr(pref, nome, bool(d[nome]))
    try:
        if "limpeza_dias" in d:
            pref.limpeza_dias = max(1, int(d["limpeza_dias"]))
        if "aviso_tamanho_mb" in d:
            pref.aviso_tamanho_mb = max(0, int(d["aviso_tamanho_mb"]))
    except (TypeError, ValueError):
        return {"ok": False}
    preferencias.salvar(pref)
    return {"ok": True, "pref": asdict(pref)}


def _alterar_pasta() -> dict:
    import webview

    janela = _e.janela()
    inicial = str(config.PASTA_PDF if config.PASTA_PDF.exists() else Path.home())
    escolhida = janela.create_file_dialog(webview.FileDialog.FOLDER, directory=inicial)
    if not escolhida:
        return {"ok": False}
    nova = escolhida[0] if isinstance(escolhida, (list, tuple)) else escolhida
    _e.pref.pasta_pdf = nova
    preferencias.salvar(_e.pref)
    preferencias.aplicar(_e.pref)
    return {"ok": True, "pasta": str(config.PASTA_PDF)}


def _abrir_pasta(qual: str) -> dict:
    pastas = {"pdf": config.PASTA_PDF, "dados": config.PASTA_DADOS, "logs": config.PASTA_LOGS}
    pasta = pastas.get(qual, config.PASTA_PDF)
    pasta.mkdir(parents=True, exist_ok=True)
    return {"ok": _abrir(pasta)}


def _abrir_arquivo(caminho: str) -> dict:
    if caminho and Path(caminho).exists():
        return {"ok": _abrir(caminho)}
    return {"ok": False, "erro": "O arquivo não está mais na pasta."}


# ======================================================== Desempenho

def _desempenho():
    from automacoes.dare import desempenho
    return desempenho


def _analise(apenas_sucesso: bool) -> dict:
    D = _desempenho()
    a = D.analisar_automacao(apenas_sucesso=apenas_sucesso)

    def est(e):
        return asdict(e)

    gargalo = ""
    if a.gargalo and a.total.media:
        e = a.etapas[a.gargalo]
        gargalo = (f"Gargalo: “{motor.ROTULO_ETAPA[a.gargalo]}” leva {D.num_br(e.media)} s em média "
                   f"({D.num_br(e.media / a.total.media * 100, 1)} % do lançamento).")
    return {
        "ok": True,
        "lotes": a.lotes, "sucessos": a.sucessos, "erros": a.erros, "execucoes": a.execucoes,
        "taxa": a.taxa_sucesso, "lotes_por_hora": a.lotes_por_hora,
        "total": est(a.total), "dare": est(a.dare), "sei": est(a.sei), "conexao": est(a.conexao),
        "etapas": [{"chave": c, "rotulo": motor.ROTULO_ETAPA[c], **est(e)} for c, e in a.etapas.items()],
        "gargalo_chave": a.gargalo, "gargalo": gargalo,
        "ultimos_totais": a.ultimos_totais,
        "dias": [{"dia": r, "ok": s, "erro": e} for r, s, e in D.contagem_historico_por_dia(14)],
        "psutil": bool(D.psutil),
    }


def _monitor(ligar: bool) -> dict:
    D = _desempenho()
    if not D.psutil:
        return {"ok": False, "erro": "O componente psutil não está instalado: o monitor não está disponível."}
    if not ligar:
        _e.monitor.clear()
        return {"ok": True}
    if _e.monitor.is_set():
        return {"ok": True}
    _e.monitor.set()

    def laco():
        monitor = D.Monitor()
        monitor.amostra()  # a 1ª leitura serve só de base para as taxas e o uso de CPU
        time.sleep(1)
        while _e.monitor.is_set():
            try:
                _e.emitir("dare_amostra", amostra=monitor.amostra())
            except Exception:  # noqa: BLE001
                pass
            for _ in range(10):
                if not _e.monitor.is_set():
                    return
                time.sleep(0.1)

    threading.Thread(target=laco, daemon=True, name="dare-monitor").start()
    return {"ok": True}


def _diagnostico() -> dict:
    D = _desempenho()

    def trabalho():
        try:
            itens = D.diagnosticar()
        except Exception as exc:  # noqa: BLE001
            itens = [D.ItemDiagnostico("Erro", "Diagnóstico", "falhou", D.ERRO, str(exc))]
        _e.ultimo_diagnostico = itens
        _e.emitir("dare_diagnostico", itens=[asdict(i) for i in itens], hora=datetime.now().strftime("%H:%M"))

    threading.Thread(target=trabalho, daemon=True, name="dare-diagnostico").start()
    return {"ok": True}


def _testes() -> dict:
    D = _desempenho()

    def progresso(i, total, nome):
        _e.emitir("dare_testes_progresso", i=i, total=total, nome=nome)

    def trabalho():
        resultados = D.rodar_benchmarks(progresso)
        try:
            D.salvar_benchmark(resultados)
        except OSError:
            pass
        _e.ultimos_testes = resultados
        anteriores = D.carregar_benchmarks()[:-1]
        linhas = []
        for r in resultados:
            valores = [x["valor"] for rodada in anteriores for x in rodada.get("resultados", [])
                       if x.get("chave") == r.chave and x.get("valor")]
            comparacao, tag = "primeira rodada", ""
            if valores and r.valor:
                media = sum(valores) / len(valores)
                delta = (r.valor - media) / media * 100
                melhor = delta > 0 if r.maior_melhor else delta < 0
                comparacao = f"{'+' if delta >= 0 else ''}{D.num_br(delta, 1)} %"
                tag = "sucesso" if melhor and abs(delta) >= 5 else ("erro" if abs(delta) >= 5 else "")
            linhas.append({"nome": r.nome, "resultado": f"{D.num_br(r.valor)} {r.unidade}" if r.valor else "—",
                           "comparacao": comparacao, "detalhe": r.detalhe, "tag": tag})
        _e.emitir("dare_testes", linhas=linhas, hora=datetime.now().strftime("%H:%M"),
                  historico=_historico_testes()["linhas"])

    threading.Thread(target=trabalho, daemon=True, name="dare-testes").start()
    return {"ok": True}


def _historico_testes() -> dict:
    D = _desempenho()
    linhas = []
    for rodada in reversed(D.carregar_benchmarks()[-30:]):
        por = {x.get("chave"): x.get("valor", 0) for x in rodada.get("resultados", [])}
        linhas.append([rodada.get("data_hora", ""), rodada.get("computador", ""),
                       D.num_br(por.get("cpu_validacao", 0), 0), D.num_br(por.get("cpu_hash", 0), 0),
                       D.num_br(por.get("planilha", 0), 0), D.num_br(por.get("disco_escrita", 0), 0),
                       D.num_br(por.get("rede_dare", 0), 0)])
    return {"ok": True, "linhas": linhas}


def _salvar_como(titulo: str, nome: str, tipos: tuple):
    import webview

    janela = _e.janela()
    caminho = janela.create_file_dialog(webview.FileDialog.SAVE, directory=str(config.BASE_DADOS),
                                        save_filename=nome, file_types=tipos)
    if not caminho:
        return None
    return caminho[0] if isinstance(caminho, (list, tuple)) else caminho


def _exportar_csv() -> dict:
    if not config.ARQ_DESEMPENHO.exists():
        return {"ok": False, "erro": "Ainda não há medições para exportar. Elas são gravadas a cada lançamento "
                                     "processado pelo aplicativo."}
    caminho = _salvar_como("Exportar medições", "desempenho_dare.csv", ("CSV (Excel) (*.csv)",))
    if not caminho:
        return {"ok": False}
    shutil.copyfile(config.ARQ_DESEMPENHO, caminho)
    return {"ok": True, "caminho": caminho}


def _relatorio(apenas_sucesso: bool) -> dict:
    D = _desempenho()
    caminho = _salvar_como("Salvar relatório de desempenho",
                           f"relatorio_desempenho_{datetime.now():%Y%m%d_%H%M}.html", ("Página HTML (*.html)",))
    if not caminho:
        return {"ok": False}
    diagnostico = getattr(_e, "ultimo_diagnostico", None)
    benchmarks = getattr(_e, "ultimos_testes", None)
    if not benchmarks:
        rodadas = D.carregar_benchmarks()
        if rodadas:
            benchmarks = [D.ResultadoBenchmark(**x) for x in rodadas[-1].get("resultados", [])]
    try:
        D.gerar_relatorio_html(Path(caminho), diagnostico or None, benchmarks or None,
                               D.analisar_automacao(apenas_sucesso=apenas_sucesso))
    except OSError as exc:
        return {"ok": False, "erro": f"Não consegui salvar o relatório: {exc}"}
    _abrir(caminho)
    return {"ok": True, "caminho": caminho, "sem_diagnostico": not diagnostico}


# ===================================================== Configurações

def _configuracoes() -> dict:
    D = _desempenho()
    exe = navegador.localizar_chrome()
    nome = f"{navegador.nome_navegador(exe)} {D.versao_navegador(exe)}".strip() if exe else ""
    recursos = {nome_arq: (config.RECURSOS / nome_arq).exists() for nome_arq in ("GUIA_DE_USO.html", "LICENCA.txt")}
    return {
        "ok": True,
        "versao": __version__, "data_versao": __data_versao__,
        "modo": "aplicativo instalado (executável)" if config.EMPACOTADO else "executando pelo código-fonte (Python)",
        "navegador": {"nome": nome, "exe": exe or "", "edge": "Edge" in nome,
                      "perfil": str(navegador.perfil_para(exe) if exe else config.PERFIL_CHROME)},
        "abrir_ao_iniciar": _e.pref.abrir_navegador_ao_iniciar,
        "pastas": [{"rotulo": "PDFs gerados", "caminho": str(config.PASTA_PDF), "qual": "pdf"},
                   {"rotulo": "Dados e histórico", "caminho": str(config.PASTA_DADOS), "qual": "dados"},
                   {"rotulo": "Logs e capturas de erro", "caminho": str(config.PASTA_LOGS), "qual": "logs"}],
        "fixos": [["Órgão", config.ORGAO], ["Código da receita", config.CODIGO_RECEITA],
                  ["Unidade gestora", config.UNIDADE_GESTORA], ["Gestão", config.GESTAO],
                  ["Valor padrão", f"R$ {config.VALOR_PADRAO}"], ["Série do documento no SEI", config.SERIE_SEI],
                  ["Site do DARE", config.URL_DARE], ["Site do SEI", config.HOST_SEI]],
        "recursos": recursos,
    }


def _abrir_recurso(nome: str) -> dict:
    if nome not in ("GUIA_DE_USO.html", "LICENCA.txt"):
        return {"ok": False}
    return _abrir_arquivo(str(config.RECURSOS / nome))


# =================================================== Importar planilha
#
# O Excel (COM) só pode ser usado na thread que o abriu, e cada chamada da página
# chega numa thread diferente. Por isso TUDO da planilha roda numa thread só, a
# _ThreadPlanilha, com o COM iniciado nela -- como na janela do DARE, onde tudo
# rodava na thread principal do Tkinter.

class _ThreadPlanilha:
    def __init__(self):
        self._fila: queue.Queue = queue.Queue()
        self._thread = None

    def _laco(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001 - sem pywin32: só leitura direta do arquivo
            pass
        while True:
            funcao, resposta = self._fila.get()
            try:
                resposta.put((True, funcao()))
            except BaseException as exc:  # noqa: BLE001
                resposta.put((False, exc))

    def executar(self, funcao):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._laco, daemon=True, name="dare-planilha")
            self._thread.start()
        resposta: queue.Queue = queue.Queue()
        self._fila.put((funcao, resposta))
        ok, valor = resposta.get()
        if not ok:
            raise valor
        return valor


_thread_planilha = _ThreadPlanilha()


class _Importacao:
    """O que a janela "Importar planilha" do DARE guardava (dialogo_planilha.py)."""

    def __init__(self):
        self.pasta = None
        self.tabela = None
        self.abertas = []
        self.lidos = None   # (ResultadoLeitura, Mapeamento)

    def fechar_pasta(self):
        if self.pasta is not None:
            try:
                self.pasta.fechar()
            except Exception:  # noqa: BLE001
                pass
        self.pasta = self.tabela = self.lidos = None


_imp = _Importacao()


def _mapa_da_tela(d: dict) -> planilha.Mapeamento:
    campos = {}
    for campo, origem in (d.get("campos") or {}).items():
        if campo not in planilha.CAMPOS or not origem:
            continue
        if origem.get("fixo") not in (None, ""):
            campos[campo] = planilha.Origem(fixo=str(origem["fixo"]).strip())
        elif origem.get("coluna"):
            campos[campo] = planilha.Origem(coluna=int(origem["coluna"]))
    try:
        linha = max(0, int(d.get("linha_cabecalho") or 0))
    except (TypeError, ValueError):
        linha = 0
    return planilha.Mapeamento(campos, linha)


def _mapa_para_tela(mapa: planilha.Mapeamento) -> dict:
    return {"linha_cabecalho": mapa.linha_cabecalho,
            "campos": {c: mapa.origem(c).para_dict() for c in planilha.CAMPOS}}


def _colunas(linha_cabecalho: int) -> dict:
    cabecalhos = planilha.ler_cabecalhos(_imp.tabela, linha_cabecalho)
    ultima = max(list(cabecalhos) + [10])
    numeros = sorted(set(cabecalhos) | set(range(1, min(ultima + 3, 60) + 1)))
    opcoes = []
    for col in numeros:
        nome = cabecalhos.get(col, "")
        letra = planilha.numero_para_letra(col)
        opcoes.append({"coluna": col, "rotulo": f"{letra}  ·  {nome}" if nome else f"Coluna {letra}"})
    encontradas = [f"{planilha.numero_para_letra(c)}: {t}" for c, t in sorted(cabecalhos.items())][:30]
    return {"opcoes": opcoes, "encontradas": encontradas}


def _sugerir_linhas(mapa: planilha.Mapeamento) -> dict:
    cab = mapa.linha_cabecalho
    saida = {"de": cab + 1 if cab else 1, "ate": "", "ultima": None}
    if mapa.colunas_usadas():
        try:
            ultima = planilha.ultima_linha_com_dados(_imp.tabela, mapa)
        except Exception:  # noqa: BLE001
            ultima = 0
        saida["ate"] = ultima or ""
        saida["ultima"] = ultima
    return saida


def _planilha(acao: str, d: dict) -> dict:
    """Os passos da janela "Importar planilha", na thread da planilha."""
    from automacoes.dare import excel_com

    if acao == "inicio":
        _imp.fechar_pasta()
        excel = planilha_arquivo.excel_disponivel()
        abertas = []
        if excel:
            try:
                _imp.abertas = excel_com.listar_abertas()
                abertas = [{"nome": p.nome, "caminho": p.caminho} for p in _imp.abertas]
            except excel_com.ExcelIndisponivel:
                excel = False
            except Exception:  # noqa: BLE001
                log.exception("Falha ao listar planilhas abertas")
                _imp.abertas = []
        return {"ok": True, "excel": excel, "abertas": abertas,
                "campos": [{"campo": c, "rotulo": planilha.ROTULOS[c], "obrigatorio": c in planilha.OBRIGATORIOS}
                           for c in planilha.CAMPOS]}

    if acao in ("aberta", "arquivo"):
        if acao == "aberta":
            i = int(d.get("indice", -1))
            if not 0 <= i < len(_imp.abertas):
                return {"ok": False, "erro": "Escolha uma das planilhas da lista."}
            pasta = _imp.abertas[i]
        else:
            try:
                pasta = planilha_arquivo.abrir(d["caminho"])
            except (FileNotFoundError, excel_com.ExcelIndisponivel) as exc:
                return {"ok": False, "erro": str(exc)}
        if _imp.pasta is not None and _imp.pasta is not pasta:
            _imp.pasta.fechar()
        _imp.pasta, _imp.tabela, _imp.lidos = pasta, None, None
        try:
            abas = pasta.abas()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "erro": f"Não consegui ler as abas: {exc}"}
        return {"ok": True, "nome": pasta.nome, "caminho": pasta.caminho, "abas": abas}

    if acao == "aba":
        try:
            _imp.tabela = _imp.pasta.tabela(d["aba"])
        except (ValueError, AttributeError) as exc:
            return {"ok": False, "erro": str(exc)}
        _imp.lidos = None
        chave = planilha.chave_mapeamento(_imp.tabela.nome, _imp.tabela.aba)
        salvo = planilha.carregar_mapeamento(chave)
        if salvo and not salvo.faltando():
            mapa, origem = salvo, "Colunas salvas da última vez para esta planilha/aba."
        else:
            linha = planilha.detectar_linha_cabecalho(_imp.tabela)
            mapa = planilha.Mapeamento(planilha.sugerir_mapeamento(planilha.ler_cabecalhos(_imp.tabela, linha)), linha)
            origem = "Colunas sugeridas pelos títulos do cabeçalho. Confira."
        return {"ok": True, "mapa": _mapa_para_tela(mapa), "origem": origem,
                "colunas": _colunas(mapa.linha_cabecalho), "linhas": _sugerir_linhas(mapa)}

    if acao == "cabecalho":
        mapa = _mapa_da_tela(d)
        _imp.lidos = None
        return {"ok": True, "colunas": _colunas(mapa.linha_cabecalho), "linhas": _sugerir_linhas(mapa)}

    if acao == "linhas":
        _imp.lidos = None
        return {"ok": True, "linhas": _sugerir_linhas(_mapa_da_tela(d))}

    if acao == "ler":
        if _imp.tabela is None:
            return {"ok": False, "erro": "Escolha uma planilha primeiro."}
        mapa = _mapa_da_tela(d)
        falta = mapa.faltando()
        if falta:
            return {"ok": False, "falta": [planilha.ROTULOS[c] for c in falta]}
        try:
            de = int(d.get("de"))
            ate = int(d["ate"]) if str(d.get("ate") or "").strip() else planilha.ultima_linha_com_dados(_imp.tabela, mapa)
        except (TypeError, ValueError):
            return {"ok": False, "erro": "Informe as linhas com números inteiros."}
        if ate < de:
            return {"ok": False, "erro": "A linha final não pode ser menor que a inicial."}
        try:
            r = planilha.ler_lotes(_imp.tabela, mapa, de, ate)
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao ler a planilha")
            return {"ok": False, "erro": f"Falha ao ler a planilha: {exc}"}
        for p in r.problemas:
            log.warning("Planilha, linha %d ignorada: %s", p.linha, p.mensagem)
        _imp.lidos = (r, mapa)
        return {"ok": True, "validas": len(r.lotes), "vazias": r.vazias, "ocultas": r.ocultas,
                "problemas": [{"linha": p.linha, "mensagem": p.mensagem} for p in r.problemas]}

    if acao == "confirmar":
        if not _imp.lidos or not _imp.lidos[0].lotes:
            return {"ok": False}
        r, mapa = _imp.lidos
        try:
            planilha.salvar_mapeamento(planilha.chave_mapeamento(_imp.tabela.nome, _imp.tabela.aba), mapa)
        except OSError:
            log.warning("Não consegui salvar o mapeamento de colunas.", exc_info=True)
        log.info("Planilha importada: %s / %s · %d lançamento(s)", _imp.tabela.nome, _imp.tabela.aba, len(r.lotes))
        if d.get("substituir"):
            _e.lotes.clear()
        _e.lotes.extend(r.lotes)
        _lotes_alterados()
        n = len(r.lotes)
        _imp.fechar_pasta()
        return {"ok": True, "n": n, "lista": _lista(), "novo": _novo()}

    if acao == "modelo":
        destino = config.PASTA_MODELOS / "modelo_dare.xlsx"
        if destino.exists() and not d.get("substituir"):
            if d.get("so_abrir"):
                _abrir(destino)
                return {"ok": True, "abriu": True}
            return {"ok": False, "existe": True}
        try:
            planilha_arquivo.criar_modelo_qualquer(destino)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "erro": f"Não consegui criar o modelo: {exc}"}
        _abrir(destino)
        return {"ok": True, "caminho": str(destino)}

    if acao == "fechar":
        _imp.fechar_pasta()
        return {"ok": True}

    return {"ok": False, "erro": f"ação desconhecida: {acao}"}


def _procurar_planilha() -> dict:
    import webview

    excel = planilha_arquivo.excel_disponivel()
    tipos = ("Planilhas do Excel (*.xlsx;*.xlsm;*.xlsb;*.xls)",) if excel else ("Planilhas do Excel (*.xlsx;*.xlsm)",)
    escolhido = _e.janela().create_file_dialog(webview.FileDialog.OPEN, file_types=tipos + ("Todos (*.*)",))
    if not escolhido:
        return {"ok": False, "cancelado": True}
    caminho = escolhido[0]
    return _thread_planilha.executar(lambda: _planilha("arquivo", {"caminho": caminho}))


# ============================================================= porta

_ACOES = {
    "estado": lambda d: _estado(),
    "novo": lambda d: {"ok": True, **_novo()},
    "validar": lambda d: _validar(d["campo"], d.get("texto", "")),
    "salvar": lambda d: _salvar(d.get("valores") or {}, d.get("indice")),
    "editar": lambda d: _editar(int(d["indice"])),
    "duplicar": lambda d: _duplicar(int(d["indice"])),
    "remover": lambda d: _remover(d.get("indices") or []),
    "esvaziar": lambda d: _esvaziar(),
    "lista": lambda d: {"ok": True, **_lista()},
    "avisos_inicio": lambda d: {"ok": True, **_avisos_inicio()},
    "iniciar": lambda d: _iniciar(),
    "login_ok": lambda d: (_e.controle.login_ok.set(), {"ok": True})[1],
    "parar": lambda d: (_e.controle.cancelar.set(), {"ok": True})[1] if _e.executando else {"ok": False},
    "abrir_navegador": lambda d: _abrir_navegador(),
    "arquivos": lambda d: _arquivos(),
    "previa": _previa,
    "limpar": _limpar,
    "salvar_pref": _salvar_pref,
    "alterar_pasta": lambda d: _alterar_pasta(),
    "abrir_pasta": lambda d: _abrir_pasta(d.get("qual", "pdf")),
    "abrir_arquivo": lambda d: _abrir_arquivo(d.get("caminho", "")),
    "analise": lambda d: _analise(bool(d.get("apenas_sucesso", True))),
    "monitor": lambda d: _monitor(bool(d.get("ligar"))),
    "diagnostico": lambda d: _diagnostico(),
    "testes": lambda d: _testes(),
    "historico_testes": lambda d: _historico_testes(),
    "exportar_csv": lambda d: _exportar_csv(),
    "relatorio": lambda d: _relatorio(bool(d.get("apenas_sucesso", True))),
    "configuracoes": lambda d: _configuracoes(),
    "abrir_recurso": lambda d: _abrir_recurso(d.get("nome", "")),
    "planilha_procurar": lambda d: _procurar_planilha(),
}


def chamar(acao: str, dados: dict | None = None) -> dict:
    """A porta única da página DARE: chamar("salvar", {...}) etc."""
    dados = dados or {}
    if acao.startswith("planilha_") and acao != "planilha_procurar":
        passo = acao[len("planilha_"):]
        return _thread_planilha.executar(lambda: _planilha(passo, dados))
    funcao = _ACOES.get(acao)
    if funcao is None:
        return {"ok": False, "erro": f"ação desconhecida: {acao}"}
    if acao != "estado":
        _iniciar_uma_vez()
    return funcao(dados)
