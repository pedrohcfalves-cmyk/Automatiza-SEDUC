"""Navegação segura: espera a tela assentar e repete quando há corrida."""

import pytest
from playwright.sync_api import Error as ErroPlaywright

from automacoes.cadastro.config import ANCORA_MANTER_CREDOR, TENTATIVAS_NAVEGACAO, URL_MANTER_CREDOR
from automacoes.cadastro.navegador import ir_para


class PaginaFalsa:
    """Página mínima que imita o postback do SIGEF atropelando o `goto`."""

    def __init__(self, interrupcoes: int = 1, erro: str = ""):
        self.interrupcoes = interrupcoes
        self.erro = erro or (
            f'Navigation to "{URL_MANTER_CREDOR}" is interrupted by another '
            'navigation to "http://sigef.sefin.ro.gov.br/outra.aspx"'
        )
        self.navegacoes = []
        self.esperas = []

    def wait_for_load_state(self, estado, timeout=None):
        self.esperas.append(estado)

    def goto(self, url, **kwargs):
        self.navegacoes.append(url)

        if self.interrupcoes > 0:
            self.interrupcoes -= 1
            raise ErroPlaywright(self.erro)

    def locator(self, seletor):
        raise AssertionError(f"âncora {seletor} não deveria ser consultada")


def test_espera_a_tela_assentar_antes_de_navegar():
    pagina = PaginaFalsa(interrupcoes=0)

    ir_para(pagina, URL_MANTER_CREDOR)

    assert pagina.navegacoes == [URL_MANTER_CREDOR]
    assert pagina.esperas[:2] == ["domcontentloaded", "networkidle"]


def test_navegacao_interrompida_e_repetida():
    pagina = PaginaFalsa()

    ir_para(pagina, URL_MANTER_CREDOR)

    assert pagina.navegacoes == [URL_MANTER_CREDOR] * 2


def test_desiste_depois_das_tentativas():
    pagina = PaginaFalsa(interrupcoes=TENTATIVAS_NAVEGACAO)

    with pytest.raises(ErroPlaywright):
        ir_para(pagina, URL_MANTER_CREDOR)

    assert len(pagina.navegacoes) == TENTATIVAS_NAVEGACAO


def test_outras_falhas_sobem_na_primeira_tentativa():
    pagina = PaginaFalsa(erro="net::ERR_CONNECTION_REFUSED")

    with pytest.raises(ErroPlaywright):
        ir_para(pagina, URL_MANTER_CREDOR, ANCORA_MANTER_CREDOR)

    assert len(pagina.navegacoes) == 1
