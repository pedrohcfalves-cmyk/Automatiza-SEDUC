"""
Configuração comum dos testes.

Rodar (na pasta do projeto, com o .venv ativado):

    pip install pytest
    python -m pytest testes -v

Os testes NÃO usam o SIGEF nem o SEI de verdade: tudo é servido por
simuladores (simulador_sigef.py / simulador_sei.py) dentro do próprio
Playwright. Nada é gravado na dados/sessao_atual.json real nem na pasta
real dos processos -- cada teste usa uma pasta temporária.

O programa fica em anexar/ (importado como automacoes.anexar.automacao.utils etc.);
as perguntas à pessoa são simuladas trocando a "tela" de
anexar/automacao/interacao.py (ver respostas() em test_ce_configuracoes.py).

O navegador dos testes é um Chromium/Chrome sem janela (headless). Ordem
de tentativa: variável CHROMIUM_TESTES (caminho do executável) ->
Chromium do Playwright -> Google Chrome instalado -> Microsoft Edge.
"""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # a pasta da Central
PASTA_TESTES = os.path.dirname(os.path.abspath(__file__))
for caminho in (RAIZ, PASTA_TESTES):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

from automacoes.anexar.automacao import utils  # noqa: E402


@pytest.fixture(autouse=True)
def registro_de_erros_tmp(tmp_path, monkeypatch):
    """registro_de_erros.txt temporário (os testes não sujam a pasta do programa)."""
    monkeypatch.setattr(utils, "CAMINHO_REGISTRO_ERROS", str(tmp_path / "registro_de_erros.txt"))


@pytest.fixture
def sessao_tmp(tmp_path, monkeypatch):
    """sessao_atual.json temporária (a real não é tocada)."""
    caminho = tmp_path / "sessao_atual.json"
    monkeypatch.setattr(utils, "CAMINHO_SESSAO", str(caminho))
    return caminho


@pytest.fixture
def pasta_base(tmp_path):
    pasta = tmp_path / "processos"
    pasta.mkdir()
    return str(pasta)


def _lancar(playwright):
    tentativas = []
    executavel = os.environ.get("CHROMIUM_TESTES")
    if executavel:
        tentativas.append({"executable_path": executavel})
    tentativas += [{}, {"channel": "chrome"}, {"channel": "msedge"}]
    if os.path.exists("/opt/pw-browsers/chromium"):
        tentativas.append({"executable_path": "/opt/pw-browsers/chromium"})
    erros = []
    for opcoes in tentativas:
        try:
            return playwright.chromium.launch(headless=True, **opcoes)
        except Exception as erro:   # noqa: BLE001
            erros.append(f"{opcoes}: {str(erro).splitlines()[0]}")
    pytest.skip("Nenhum Chromium/Chrome disponível para os testes:\n" + "\n".join(erros))


@pytest.fixture(scope="session")
def navegador():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = _lancar(playwright)
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture
def context(navegador):
    ctx = navegador.new_context(accept_downloads=True)
    ctx.set_default_timeout(15000)
    yield ctx
    ctx.close()
