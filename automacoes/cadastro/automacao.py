"""Fluxo da automação no SIGEF: credor e domicílio bancário."""

import re
import time
from typing import Callable, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .bancos import normalizar
from .config import (
    ANCORA_DOMICILIO,
    ANCORA_MANTER_CREDOR,
    DELAY_DIGITACAO,
    DOMINIO,
    ESPERA_MENSAGEM,
    JA_CADASTRADO,
    SELETOR_CREDOR,
    SELETOR_MENSAGEM,
    TIPO_CREDOR,
    URL_INCLUIR_DOMICILIO,
    URL_MANTER_CREDOR,
)
from .estatisticas import EXISTENTE, NOVO
from .log import logger
from .modelos import Lote, PularLote, ReiniciarLote, Resposta
from .navegador import esperar_carregar, esperar_elemento, ir_para

# Ações que podem ser conferidas manualmente antes do clique
INCLUIR_CREDOR = "Incluir novo credor"
CONFIRMAR_DOMICILIO = "Confirmar inclusão do domicílio bancário"

# perguntar(lote, ação, editável) -> Resposta
Perguntar = Callable[[Lote, str, bool], Resposta]


class Confirmador:
    """Acompanha um lote: confere os dados antes do clique (se houver `perguntar`).

    Também anota, para as estatísticas, o caminho seguido (credor novo ou já
    existente) e quanto tempo a pessoa levou respondendo às conferências.
    """

    def __init__(self, perguntar: Optional[Perguntar] = None, editavel: bool = True):
        self.perguntar = perguntar
        self.editavel = editavel
        self.lote_liberado = False
        self.caminho = ""
        self.espera = 0.0

    def clicar(self, locator, lote: Lote, acao: str) -> None:
        if self.perguntar and not self.lote_liberado:
            inicio = time.perf_counter()
            try:
                resposta = self.perguntar(lote, acao, self.editavel)
            finally:
                self.espera += time.perf_counter() - inicio

            if resposta is Resposta.SIM_TODOS:
                self.lote_liberado = True
            elif resposta is Resposta.CORRIGIR and self.editavel:
                raise ReiniciarLote
            elif resposta is Resposta.PULAR:
                raise PularLote

        locator.click()


def fechar_popups(context, page: Page) -> None:
    """Garante que o próximo lote comece apenas com a aba principal."""
    for aba in list(context.pages):
        if aba is not page and DOMINIO in aba.url.lower():
            try:
                aba.close()
            except Exception:
                pass


def navegador_fechado(page: Page) -> bool:
    """True quando a aba ou o navegador foram fechados durante a execução."""
    try:
        browser = page.context.browser
        return page.is_closed() or (browser is not None and not browser.is_connected())
    except Exception:
        return True


def esperar_mensagem(page: Page, timeout: Optional[int] = None):
    """Espera a mensagem do SIGEF aparecer, qualquer que seja o resultado.

    Sem `timeout`, vale o prazo padrão do navegador.
    """
    mensagem = page.locator(SELETOR_MENSAGEM).first

    try:
        mensagem.wait_for(state="visible", timeout=timeout)
    except PlaywrightTimeout:
        return None

    return mensagem


def ler_mensagem(page: Page) -> tuple:
    """Lê o retorno do SIGEF: ("OK" | "JA" | "ERRO", texto)."""
    mensagem = esperar_mensagem(page)

    if mensagem is None:
        return "ERRO", "Sem mensagem de retorno do SIGEF"

    classe = mensagem.get_attribute("class") or ""
    texto = " ".join((mensagem.inner_text() or "").split())

    if "Sucesso" in classe:
        return "OK", texto or classe

    # "Domicílio já cadastrado" é erro para o SIGEF, mas aqui significa feito
    if JA_CADASTRADO in re.sub(r"[^A-Z]", "", normalizar(texto)):
        return "JA", texto

    return "ERRO", texto or classe


def digitar(page: Page, seletor: str, texto: str) -> None:
    """Digita devagar num campo que pesquisa sozinho enquanto recebe as teclas."""
    esperar_elemento(page, seletor).press_sequentially(texto, delay=DELAY_DIGITACAO)


def incluir_domicilio(page: Page, lote: Lote, confirmador: Confirmador) -> tuple:
    """Cadastra o domicílio bancário de um credor já existente."""
    ir_para(page, URL_INCLUIR_DOMICILIO, ANCORA_DOMICILIO)

    with page.expect_popup() as popup_info:
        page.locator(ANCORA_DOMICILIO).click()

    pesquisa = popup_info.value
    esperar_carregar(pesquisa)

    esperar_elemento(pesquisa, "#btnCPF").click()
    esperar_elemento(pesquisa, "#txtNuCpf").fill(lote.cpf)
    pesquisa.locator("#btnConfirmar").click()
    esperar_carregar(pesquisa)

    esperar_elemento(pesquisa, SELETOR_CREDOR).click()

    page.bring_to_front()
    digitar(page, "#txtBanco_SIGEFPesquisa", lote.banco)
    digitar(page, "#txtAgBancaria_SIGEFPesquisa", lote.agencia)
    digitar(page, "#txtContaBancaria", lote.conta)
    page.locator("#txtNmContaBancaria").fill(lote.nome)
    confirmador.clicar(page.locator("#btnConfirmar"), lote, CONFIRMAR_DOMICILIO)

    return ler_mensagem(page)


def processar_lote(page: Page, lote: Lote, confirmador: Confirmador) -> tuple:
    """Executa um lote completo e devolve ("OK" | "JA" | "ERRO", mensagem)."""
    # Volta sempre para a tela inicial do loop
    ir_para(page, URL_MANTER_CREDOR, ANCORA_MANTER_CREDOR)

    page.locator(ANCORA_MANTER_CREDOR).select_option(TIPO_CREDOR)

    with page.expect_popup() as popup_info:
        page.locator("#btnManutencao_BtnListar").click()

    pesquisa = popup_info.value
    esperar_carregar(pesquisa)

    esperar_elemento(pesquisa, "#txtCPF").fill(lote.cpf)
    pesquisa.locator("#btnConfirmar").click()
    esperar_carregar(pesquisa)  # sem isso a contagem abaixo leria a tela anterior

    cadastro = pesquisa.locator(SELETOR_CREDOR)

    if cadastro.count() == 0:
        # ---------- CAMINHO 1: credor inexistente, cadastrar ----------
        confirmador.caminho = NOVO
        pesquisa.close()
        page.bring_to_front()
        esperar_elemento(page, "#txtCPF").fill(lote.cpf)
        page.locator("#btnReceitaFederal").click()
        esperar_carregar(page)  # a consulta à Receita recarrega a tela
        esperar_elemento(page, "#txtNmCredor").fill(lote.nome)
        confirmador.clicar(page.locator("#btnManutencao_BtnIncluir"), lote, INCLUIR_CREDOR)

        # O SIGEF demora para responder: espera o aviso de sucesso ou de erro
        esperar_mensagem(page, ESPERA_MENSAGEM)

    else:
        # ---------- CAMINHO 2: credor já cadastrado ----------
        confirmador.caminho = EXISTENTE
        cadastro.first.click()
        page.bring_to_front()

    resultado = incluir_domicilio(page, lote, confirmador)
    logger.info("%s -> %s %s", lote.cpf, *resultado)

    return resultado


def descrever_erro(erro: Exception) -> str:
    """Motivo curto de uma falha, pronto para a planilha (sem o prefixo ERRO)."""
    if isinstance(erro, PlaywrightTimeout):
        return "timeout - elemento não encontrado"

    return (str(erro).splitlines() or [type(erro).__name__])[0]
