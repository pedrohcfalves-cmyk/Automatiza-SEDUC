"""
Motor de execução usado pelo aplicativo com janela.

Faz o mesmo que o loop do modo terminal (dare_automacao.executar_lotes): para cada processo,
gera os DAREs (PDFs) de todos os seus lançamentos, junta os PDFs num só arquivo e anexa esse
arquivo UMA vez no SEI, seguindo para o próximo se um falhar. A diferença é que roda numa thread
separada (a janela continua respondendo), avisa a janela por "eventos" e MEDE o tempo de
cada etapa, gravando em dados/desempenho.csv (usado na aba Desempenho).

Os passos nos sites continuam em dare.py e sei.py, sem nenhuma mudança: os tempos são
medidos pelas próprias mensagens de log de cada passo (ex.: "DARE 3/5", "SEI 2/4").
"""

import csv
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import armazenamento, config, dare, juntar, navegador, sei, utils
from .modelos import DadosDare, ResultadoLote

try:  # o aplicativo abre mesmo sem o Playwright; o erro só aparece ao executar
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depende do ambiente
    sync_playwright = None

log = logging.getLogger("dare.motor")

Emissor = Callable[[str, dict], None]

# Etapas medidas: (chave, rótulo, início da mensagem de log que marca o começo da etapa)
ETAPAS = [
    ("preparo", "Preparar formulário", None),
    ("dare_1", "DARE · órgão e contribuinte", "DARE 1/5"),
    ("dare_2", "DARE · receita e gestão", "DARE 2/5"),
    ("dare_3", "DARE · CPF do servidor", "DARE 3/5"),
    ("dare_4", "DARE · referência e valor", "DARE 4/5"),
    ("dare_5", "DARE · imprimir e salvar PDF", "DARE 5/5"),
    ("retorno", "Voltar ao formulário", "PDF salvo em"),
    ("sei_1", "SEI · abrir processo", "SEI 1/4"),
    ("sei_2", "SEI · incluir documento", "SEI 2/4"),
    ("sei_3", "SEI · documento externo", "SEI 3/4"),
    ("sei_4", "SEI · anexar e salvar", "SEI 4/4"),
]
ROTULO_ETAPA = {chave: rotulo for chave, rotulo, _ in ETAPAS}
COLUNAS_DESEMPENHO = (
    ["data_hora", "execucao", "lote", "total_lotes", "origem", "status", "conexao_s", "total_s",
     "dare_s", "sei_s"] + [f"{chave}_s" for chave, _, _ in ETAPAS]
)


class Cancelado(Exception):
    """O usuário pediu para parar enquanto o programa esperava."""


@dataclass
class Controle:
    """Comunicação da janela com a thread: parar e confirmar o login."""

    cancelar: threading.Event = field(default_factory=threading.Event)
    login_ok: threading.Event = field(default_factory=threading.Event)


# Durante a sessão do programa, o login só é pedido uma vez (como no modo terminal).
_sessao = {"login_confirmado": False}


def login_ja_confirmado() -> bool:
    return _sessao["login_confirmado"]


# ---- Medição das etapas -------------------------------------------------------------------

class MedidorEtapas(logging.Handler):
    """Guarda o instante (perf_counter) em que cada etapa começou, a partir das mensagens de log."""

    def __init__(self, ao_mudar_etapa: Callable[[str], None] | None = None):
        super().__init__(level=logging.INFO)
        self.marcas: dict[str, float] = {}
        self.ao_mudar_etapa = ao_mudar_etapa

    def reiniciar(self, preparo: bool = True) -> None:
        """Zera as marcas; com `preparo`, a etapa "Preparar formulário" começa agora."""
        self.marcas = {"preparo": time.perf_counter()} if preparo else {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        for chave, _, prefixo in ETAPAS:
            if prefixo and msg.startswith(prefixo) and chave not in self.marcas:
                self.marcas[chave] = time.perf_counter()
                if self.ao_mudar_etapa:
                    self.ao_mudar_etapa(chave)
                break

    def duracoes(self, fim: float) -> dict[str, float]:
        """Segundos de cada etapa alcançada (a última vai até `fim`)."""
        alcancadas = [(c, self.marcas[c]) for c, _, _ in ETAPAS if c in self.marcas]
        saida: dict[str, float] = {}
        for i, (chave, inicio) in enumerate(alcancadas):
            termino = alcancadas[i + 1][1] if i + 1 < len(alcancadas) else fim
            saida[chave] = max(0.0, termino - inicio)
        return saida


def _registrar_desempenho(linha: dict) -> None:
    """Acrescenta uma linha em dados/desempenho.csv (sem CPF nem processo: só tempos)."""
    try:
        config.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        novo = not config.ARQ_DESEMPENHO.exists()
        with open(config.ARQ_DESEMPENHO, "a", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, COLUNAS_DESEMPENHO, delimiter=";", extrasaction="ignore")
            if novo:
                escritor.writeheader()
            escritor.writerow(linha)
    except OSError:
        log.warning("Não consegui gravar o desempenho.", exc_info=True)


def _fmt(segundos: float | None) -> str:
    return "" if segundos is None else f"{segundos:.3f}".replace(".", ",")


# ---- Execução -----------------------------------------------------------------------------

def _resumo_erro(exc: BaseException) -> str:
    texto = str(exc)
    return f"{type(exc).__name__}: {texto.splitlines()[0] if texto else ''}"


def _rotulo(i: int, total: int, dados: DadosDare) -> str:
    texto = f"Lote {i}/{total}"
    return f"{texto} ({dados.origem})" if dados.origem else texto


def _aguardar_login(emitir: Emissor, controle: Controle) -> None:
    if _sessao["login_confirmado"]:
        return
    controle.login_ok.clear()
    emitir("aguardando_login", {})
    log.info("Aguardando o login no DARE e no SEI.")
    while not controle.login_ok.wait(0.2):
        if controle.cancelar.is_set():
            raise Cancelado()
    _sessao["login_confirmado"] = True
    emitir("login_confirmado", {})


@dataclass
class _Gerado:
    """DARE já gerado, esperando o anexo (junto com os outros do mesmo processo) no SEI."""

    indice: int
    dados: DadosDare
    pdf: str
    servidor: str
    dare_s: float
    duracoes: dict[str, float]


def executar(lotes: list[DadosDare], emitir: Emissor, controle: Controle
             ) -> tuple[list[ResultadoLote], bool]:
    """
    Processa os lançamentos numa única conexão com o navegador, processo a processo:
    gera os DAREs de cada processo, junta os PDFs num só e anexa esse arquivo UMA vez no SEI.
    Os lançamentos são reordenados para que os do mesmo processo fiquem seguidos (os
    índices dos eventos se referem a essa ordem; a janela usa juntar.ordenar_por_processo).
    Devolve (resultados, interrompido). Nunca levanta exceção: erros viram resultados.
    """
    lotes = juntar.ordenar_por_processo(lotes)
    total = len(lotes)
    feitos: dict[int, ResultadoLote] = {}  # índice (base 1) -> resultado
    interrompido = False
    conexao: float | None = None
    execucao = datetime.now().strftime("%Y%m%d-%H%M%S")
    medidor = MedidorEtapas(lambda chave: emitir("etapa", {"etapa": chave,
                                                            "rotulo": ROTULO_ETAPA[chave]}))
    raiz = logging.getLogger("dare")
    if not raiz.isEnabledFor(logging.INFO):  # as etapas são medidas pelas mensagens INFO
        raiz.setLevel(logging.INFO)
    raiz.addHandler(medidor)
    emitir("inicio", {"total": total})
    armazenamento.salvar_lote(lotes)  # sobrevive a erro ou queda do computador

    def concluir(i: int, dados: DadosDare, erro: str, pdf: str, servidor: str, dare_s: float,
                 sei_s: float | None, duracoes: dict[str, float], extra: str = "") -> None:
        """Registra o resultado de um lançamento (histórico, desempenho) e avisa a janela."""
        rotulo = _rotulo(i, total, dados)
        sucesso = not erro
        status = "SUCESSO" if sucesso else "ERRO"
        obs = " · ".join(p for p in (rotulo, extra, erro) if p)[:300]
        armazenamento.registrar_historico(dados, status, servidor, pdf, obs)
        resultado = ResultadoLote(dados, sucesso, pdf, servidor, erro)
        feitos[i] = resultado
        segundos = dare_s + (sei_s or 0.0)
        linha = {
            "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "execucao": execucao, "lote": i, "total_lotes": total,
            "origem": "planilha" if dados.origem else "digitado", "status": status,
            "conexao_s": _fmt(conexao) if i == 1 else "",
            "total_s": _fmt(segundos),
            "dare_s": _fmt(dare_s),
            "sei_s": _fmt(sei_s),
        }
        linha.update({f"{c}_s": _fmt(s) for c, s in duracoes.items()})
        _registrar_desempenho(linha)
        emitir("lote_fim", {"indice": i, "total": total, "resultado": resultado,
                            "segundos": segundos, "etapas": duracoes})

    try:
        if sync_playwright is None:
            raise RuntimeError("O componente Playwright não está instalado.")
        t0 = time.perf_counter()
        emitir("status", {"texto": "Abrindo e conectando ao navegador..."})
        if not navegador.garantir_chrome():
            raise navegador.ChromeNaoEncontrado(
                "Não consegui abrir o navegador em modo depuração. Feche todas as janelas do "
                "navegador de depuração e tente de novo."
            )
        with sync_playwright() as p:
            _, context = navegador.conectar(p)
            context.add_init_script(
                f"if (location.hostname.includes('{config.HOST_DARE}')) "
                "window.print = () => {};"
            )
            page_sei, _ = navegador.obter_aba(context, config.HOST_SEI, config.URL_SEI)
            page, dare_criada = navegador.obter_aba(context, config.HOST_DARE, config.URL_DARE)
            navegador.ativar_aba(context, page)
            if not dare_criada:
                page.goto(config.URL_DARE)
            page.wait_for_load_state("networkidle")
            conexao = time.perf_counter() - t0
            emitir("conectado", {"segundos": conexao})

            _aguardar_login(emitir, controle)

            for grupo in juntar.agrupar_por_processo(lotes):
                if controle.cancelar.is_set():
                    interrompido = True
                    i = grupo[0] + 1
                    log.warning("Execução interrompida pelo usuário antes do %s.",
                                _rotulo(i, total, lotes[i - 1]))
                    break

                # 1) Gera os DAREs (PDFs) de todos os lançamentos deste processo
                gerados: list[_Gerado] = []
                for pos, indice in enumerate(grupo):
                    i, dados = indice + 1, lotes[indice]
                    rotulo = _rotulo(i, total, dados)
                    if pos and controle.cancelar.is_set():
                        interrompido = True
                        log.warning("Execução interrompida pelo usuário antes do %s.", rotulo)
                        break
                    emitir("lote_inicio", {"indice": i, "total": total, "dados": dados})
                    armazenamento.salvar_ultimos(dados)
                    log.info(
                        "=== %s · processo %s · CPF %s · venc %s · R$ %s ===",
                        rotulo, dados.processo, utils.mascarar_cpf(dados.cpf),
                        dados.vencimento.strftime("%d/%m/%Y"), dados.valor,
                    )
                    medidor.reiniciar()
                    inicio = time.perf_counter()
                    servidor, pdf, erro = "", "", ""
                    try:
                        page = navegador.garantir_aba(context, page, config.HOST_DARE, config.URL_DARE)
                        navegador.ativar_aba(context, page)
                        if i > 1:
                            page.goto(config.URL_DARE)
                        page.wait_for_load_state("networkidle")
                        caminho_pdf, servidor = dare.gerar_dare(context, page, dados)
                        pdf = str(caminho_pdf)
                    except Exception as exc:  # noqa: BLE001 - registra e segue para o próximo
                        navegador.capturar_erro(context)
                        log.exception("Falha em %s", rotulo)
                        erro = _resumo_erro(exc)
                    fim = time.perf_counter()
                    duracoes = medidor.duracoes(fim)
                    if erro:
                        concluir(i, dados, erro, pdf, servidor, fim - inicio, None, duracoes)
                    else:
                        gerados.append(_Gerado(i, dados, pdf, servidor, fim - inicio, duracoes))
                        emitir("lote_pdf", {"indice": i, "total": total, "pdf": pdf,
                                            "servidor": servidor, "segundos": fim - inicio})

                if not gerados:
                    if interrompido:
                        break
                    continue

                # 2) Junta os PDFs e anexa UM arquivo no SEI para o processo
                processo = gerados[0].dados.processo
                emitir("sei_inicio", {"indices": [g.indice for g in gerados], "processo": processo,
                                      "quantidade": len(gerados)})
                medidor.reiniciar(preparo=False)
                inicio_sei = time.perf_counter()
                erro_sei, anexos = "", []
                try:
                    anexos = juntar.preparar_anexos([Path(g.pdf) for g in gerados], processo)
                    for arquivo in anexos:
                        page_sei = sei.anexar_pdf(context, page_sei, gerados[0].dados, arquivo)
                except Exception as exc:  # noqa: BLE001 - registra e segue para o próximo processo
                    navegador.capturar_erro(context)
                    log.exception("Falha ao anexar no SEI o processo %s", processo)
                    erro_sei = _resumo_erro(exc)
                fim_sei = time.perf_counter()
                etapas_sei = medidor.duracoes(fim_sei)
                if "sei_1" in medidor.marcas:  # o tempo de juntar os PDFs entra em "abrir processo"
                    etapas_sei["sei_1"] += medidor.marcas["sei_1"] - inicio_sei

                # O tempo do SEI é dividido entre os DAREs anexados juntos.
                n = len(gerados)
                extra = ""
                if n > 1 and len(anexos) == 1:
                    extra = f"anexado junto com outros {n - 1} DARE(s) em {anexos[0].name}"
                for g in gerados:
                    duracoes = dict(g.duracoes)
                    duracoes.update({c: s / n for c, s in etapas_sei.items()})
                    concluir(g.indice, g.dados, erro_sei, g.pdf, g.servidor, g.dare_s,
                             (fim_sei - inicio_sei) / n, duracoes, extra)
                if interrompido:
                    break
    except Cancelado:
        interrompido = True
        log.warning("Execução cancelada pelo usuário.")
    except Exception as exc:  # noqa: BLE001 - falha geral (ex.: navegador fechado)
        log.exception("Falha geral na execução")
        resumo = _resumo_erro(exc)
        emitir("erro_geral", {"mensagem": resumo})
        # Tudo o que não terminou fica com este erro (inclusive DAREs gerados e não anexados).
        for i in range(1, total + 1):
            if i in feitos:
                continue
            dados = lotes[i - 1]
            rotulo = _rotulo(i, total, dados)
            armazenamento.registrar_historico(dados, "ERRO", "", "", f"{rotulo} · {resumo}"[:300])
            feitos[i] = ResultadoLote(dados, False, "", "", resumo)
    finally:
        raiz.removeHandler(medidor)

    # Na ordem dos lançamentos (os processados são sempre os primeiros da lista).
    resultados = [feitos[i] for i in sorted(feitos)]
    # Pendentes = os que falharam + os que nem chegaram a ser processados.
    pendentes = [d for d, r in zip(lotes, resultados) if not r.sucesso] + lotes[len(resultados):]
    try:
        if pendentes:
            armazenamento.salvar_lote(pendentes)
        else:
            armazenamento.limpar_lote()
    except OSError:
        log.warning("Não consegui atualizar os lançamentos pendentes.", exc_info=True)

    log.info("=== Fim: %s de %s com sucesso%s ===", sum(r.sucesso for r in resultados), total,
             " (interrompido)" if interrompido else "")
    emitir("fim", {"resultados": resultados, "interrompido": interrompido,
                   "pendentes": pendentes, "total": total})
    return resultados, interrompido


def iniciar_em_thread(lotes: list[DadosDare], emitir: Emissor, controle: Controle) -> threading.Thread:
    """Roda `executar` numa thread em segundo plano e devolve a thread."""
    def alvo():
        try:
            executar(lotes, emitir, controle)
        except Exception as exc:  # noqa: BLE001 - nunca deixa a thread morrer em silêncio
            log.exception("Erro inesperado no motor")
            emitir("fim", {"resultados": [], "interrompido": True, "pendentes": list(lotes),
                           "total": len(lotes), "erro": str(exc)})

    thread = threading.Thread(target=alvo, name="dare-motor", daemon=True)
    thread.start()
    return thread


def abrir_navegador_em_thread(ao_terminar: Callable[[bool], None]) -> threading.Thread:
    """Abre o navegador de depuração sem travar a janela."""
    def alvo():
        try:
            ok = navegador.garantir_chrome()
        except Exception:  # noqa: BLE001
            log.exception("Falha ao abrir o navegador")
            ok = False
        ao_terminar(ok)

    thread = threading.Thread(target=alvo, name="dare-navegador", daemon=True)
    thread.start()
    return thread

