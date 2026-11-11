"""Fixtures: SIGEF simulado + Chromium em modo de depuração apontando para ele.

O domínio real do SIGEF é redirecionado para o simulado (--host-resolver-rules),
então a automação roda exatamente com as URLs de produção.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent  # a pasta da Central
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sigef_simulado import criar_servidor  # noqa: E402
from automacoes.cadastro.config import CDP_URL, DOMINIO, PORTA_DEBUG, URL_SIGEF  # noqa: E402
from automacoes.cadastro.navegador import cdp_disponivel  # noqa: E402

PORTA_SIGEF = 80  # o domínio é mapeado só pelo nome; a porta precisa ser a 80


def _chromium() -> str:
    candidatos = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    candidatos += [shutil.which(nome) or "" for nome in ("chromium", "google-chrome")]
    return next((c for c in candidatos if c and os.path.isfile(c)), "")


@pytest.fixture(scope="session")
def servidor():
    srv = criar_servidor(PORTA_SIGEF)
    yield srv
    srv.shutdown()


@pytest.fixture(scope="session")
def chromium(servidor):
    executavel = _chromium()

    if not executavel:
        pytest.skip("Chromium não disponível")

    perfil = tempfile.mkdtemp(prefix="sigef-teste-")
    processo = subprocess.Popen(
        [
            executavel,
            f"--remote-debugging-port={PORTA_DEBUG}",
            f"--user-data-dir={perfil}",
            f"--host-resolver-rules=MAP {DOMINIO} 127.0.0.1",
            "--disable-features=HttpsUpgrades,HttpsFirstBalancedModeAutoEnable",
            "--no-proxy-server",
            "--no-first-run",
            "--no-sandbox",
            "--headless=new",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    assert cdp_disponivel(20), f"Chromium não respondeu em {CDP_URL}"
    yield processo

    processo.terminate()
    processo.wait(10)
    shutil.rmtree(perfil, ignore_errors=True)


@pytest.fixture(scope="session")
def playwright():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw


def fazer_login(page) -> None:
    page.goto(URL_SIGEF)
    page.locator("#usuario").fill("teste")
    page.locator("#entrar").click()
    page.locator("#bemvindo").wait_for()


@pytest.fixture()
def navegador(chromium, playwright, servidor):
    from automacoes.cadastro.navegador import Navegador

    nav = Navegador(playwright)
    nav.abrir()
    nav.context.set_default_timeout(3000)  # simulado responde rápido
    fazer_login(nav.page)
    yield nav
    time.sleep(0.2)


@pytest.fixture(autouse=True)
def estatisticas_isoladas(tmp_path, monkeypatch):
    """Cada teste grava as estatísticas numa pasta temporária, nunca na real."""
    from automacoes.cadastro import estatisticas

    pasta = tmp_path / "estatisticas"
    monkeypatch.setattr(estatisticas, "PASTA_ESTATISTICAS", pasta)
    monkeypatch.setattr(estatisticas, "PASTA_IMPORTADOS", pasta / "outros-computadores")
    monkeypatch.setattr(estatisticas, "ARQUIVO_AJUSTES", pasta / "ajustes.json")
    monkeypatch.setattr(estatisticas, "_pasta_do_programa", lambda: tmp_path)
    return pasta
