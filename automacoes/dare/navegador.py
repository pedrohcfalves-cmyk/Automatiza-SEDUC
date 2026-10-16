"""Controle do Chrome em modo depuração: abas, busca em iframes, PDF e capturas de erro."""

import base64
import logging
import os
import shutil
import socket
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from . import config, utils

log = logging.getLogger("dare.navegador")

_SESSOES_FOCO: list = []  # mantém as sessões CDP vivas para o "foco" continuar ativo


class ChromeNaoEncontrado(RuntimeError):
    """O Chrome não está aberto com --remote-debugging-port."""


def chrome_debug_ativo(timeout: float = 0.4) -> bool:
    """Teste rápido (sem Playwright): a porta de depuração do Chrome está aceitando conexão?"""
    try:
        with socket.create_connection(("127.0.0.1", config.PORTA_CDP), timeout=timeout):
            return True
    except OSError:
        return False


def localizar_chrome() -> str | None:
    """
    Caminho do navegador: variável DARE_CHROME_PATH, Chrome nos locais padrão do Windows ou
    no PATH. Se o Chrome não estiver instalado, usa o Microsoft Edge (que vem com o Windows
    10/11 e aceita o mesmo modo de depuração), para o programa funcionar em qualquer computador.
    """
    candidatos = [os.environ.get("DARE_CHROME_PATH", "")]
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            candidatos.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    candidatos.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            return caminho
    for nome in ("chrome", "google-chrome", "google-chrome-stable", "chromium"):
        achado = shutil.which(nome)
        if achado:
            return achado
    return localizar_edge()


def localizar_edge() -> str | None:
    """Caminho do Microsoft Edge (alternativa quando o Chrome não está instalado)."""
    for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            caminho = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(caminho):
                return caminho
    return None


def nome_navegador(exe: str | None) -> str:
    """'Microsoft Edge' ou 'Google Chrome', conforme o executável."""
    return "Microsoft Edge" if exe and "msedge" in os.path.basename(exe).lower() else "Google Chrome"


def perfil_para(exe: str) -> Path:
    """Perfil do navegador de depuração: um para o Chrome e outro para o Edge (não se misturam)."""
    return config.PERFIL_EDGE if "msedge" in os.path.basename(exe).lower() else config.PERFIL_CHROME


def iniciar_chrome(espera: float = config.ESPERA_CHROME) -> bool:
    """
    Abre o Chrome em modo depuração com as duas abas (SEI e DARE) e espera a porta responder.
    Se o Chrome de depuração já estiver aberto, não faz nada. Devolve True se está pronto.
    """
    if chrome_debug_ativo():
        return True
    exe = localizar_chrome()
    if exe is None:
        log.error("Chrome não encontrado. Defina DARE_CHROME_PATH com o caminho do chrome.exe.")
        return False

    perfil = perfil_para(exe)
    perfil.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={config.PORTA_CDP}",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        config.URL_SEI,
        config.URL_DARE,
    ]
    opcoes: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        opcoes["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        opcoes["start_new_session"] = True
    log.info("Abrindo o %s em modo depuração (SEI e DARE).", nome_navegador(exe))
    subprocess.Popen(args, **opcoes)

    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        if chrome_debug_ativo():
            log.info("Chrome pronto na porta %s.", config.PORTA_CDP)
            return True
        time.sleep(0.5)
    log.error(
        "O navegador abriu, mas a porta %s não respondeu. Feche TODAS as janelas que usam o "
        "perfil '%s' e tente de novo.", config.PORTA_CDP, perfil,
    )
    return False


def garantir_chrome() -> bool:
    """Abre o Chrome de depuração se ainda não estiver aberto. True se está pronto."""
    return chrome_debug_ativo() or iniciar_chrome()


def conectar(playwright):
    """Conecta ao Chrome já aberto e devolve (browser, contexto)."""
    try:
        browser = playwright.chromium.connect_over_cdp(config.CDP_URL)
    except Exception as exc:
        raise ChromeNaoEncontrado(
            "Chrome em modo de depuração não encontrado. "
            "Abra-o com o arquivo 'iniciar_chrome_debug.bat'."
        ) from exc
    log.info("Conectado ao Chrome (%s).", config.CDP_URL)
    return browser, browser.contexts[0]


# ---- Abas ---------------------------------------------------------------------------------

def obter_aba(context, host: str, url: str):
    """Reaproveita a aba já aberta do site (pelo host) ou abre uma nova. -> (aba, foi_criada)"""
    for tentativa in range(20):
        for aba in context.pages:
            if host in aba.url.lower():
                log.info("Aba encontrada: %s", host)
                return aba, False
        # Chrome recém-aberto: as abas ainda podem estar em branco, carregando. Espera um pouco
        # antes de concluir que a aba não existe (evita abrir uma aba duplicada).
        carregando = any(
            aba.url in ("", "about:blank") or aba.url.startswith("chrome://")
            for aba in context.pages
        )
        if not carregando:
            break
        time.sleep(0.5)
    log.info("Aba de %s não encontrada; abrindo uma nova.", host)
    aba = context.new_page()
    aba.goto(url)
    return aba, True


def garantir_aba(context, atual, host: str, url: str):
    """
    Devolve a aba do site: a atual, se ainda for válida; senão procura pelo host entre as
    abas abertas; se não achar, abre uma nova. Assim a aba é sempre re-encontrada, mesmo que
    você tenha trocado de aba, navegado ou fechado alguma enquanto o script esperava.
    """
    if atual is not None and not atual.is_closed() and host in atual.url.lower():
        return atual
    aba, _ = obter_aba(context, host, url)
    return aba


def ativar_aba(context, page) -> None:
    """
    Traz a aba para frente e a mantém ATIVA. Abas em segundo plano são congeladas pelo Chrome
    (a automação para até você abri-las manualmente); isso evita o problema nos dois sentidos
    (DARE -> SEI e SEI -> DARE).
    """
    page.bring_to_front()
    try:
        sessao = context.new_cdp_session(page)
        sessao.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        _SESSOES_FOCO.append(sessao)
    except Exception:  # noqa: BLE001 - não é essencial; segue só com o bring_to_front
        log.debug("Não foi possível ativar a emulação de foco.", exc_info=True)
    try:
        page.wait_for_function("document.visibilityState === 'visible'", timeout=5000)
    except PlaywrightTimeoutError:
        log.debug("Aba ainda não está 'visible'; tentando de novo.")
        page.bring_to_front()
        page.wait_for_timeout(500)


# ---- Elementos ----------------------------------------------------------------------------

def achar_visivel(page, seletor: str, timeout: float = config.TIMEOUT_ELEMENTO,
                  exigir_visivel: bool = True):
    """
    Procura o seletor na página E em todos os iframes (o SEI mostra o processo dentro de
    iframes aninhados) e devolve o primeiro elemento visível. Espera até `timeout` segundos.
    Com exigir_visivel=False basta o elemento existir (útil para <input type="file">).
    """
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        for frame in page.frames:
            try:
                candidato = frame.locator(seletor).first
                if candidato.count() and (not exigir_visivel or candidato.is_visible()):
                    return candidato
            except Exception:  # noqa: BLE001 - frame recarregando; tenta no próximo ciclo
                pass
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError(f"Elemento não encontrado em nenhum frame: {seletor}")


def aguardar_sumir(page, seletor: str, timeout: float = 15) -> bool:
    """Espera o elemento deixar de estar visível em todos os frames. False se continuar lá."""
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        visivel = False
        for frame in page.frames:
            try:
                if frame.locator(seletor).first.is_visible():
                    visivel = True
                    break
            except Exception:  # noqa: BLE001 - frame recarregando conta como "não visível"
                continue
        if not visivel:
            return True
        page.wait_for_timeout(250)
    return False


def preencher_data_hoje(page, seletor: str = "#txtDataElaboracao", tentativas: int = 6) -> None:
    """
    Preenche o campo com a data de hoje (DD/MM/AAAA) digitando tecla a tecla, para a máscara
    do SEI (infraMascaraData, no onkeypress) funcionar, e confere se o valor ficou no campo.
    Repete se a tela recarregar e limpar o campo.
    """
    esperado = date.today().strftime("%d/%m/%Y")
    for tentativa in range(1, tentativas + 1):
        try:
            campo = achar_visivel(page, seletor)
            campo.click()
            campo.fill("")
            campo.press_sequentially(utils.somente_digitos(esperado), delay=60)
            page.wait_for_timeout(500)  # dá tempo de um eventual recarregamento limpar o campo
            if achar_visivel(page, seletor).input_value() == esperado:
                return
        except PlaywrightTimeoutError:
            raise
        except Exception:  # noqa: BLE001 - frame recarregou no meio da digitação
            log.debug("Falha ao digitar a data (tentativa %s).", tentativa, exc_info=True)
        page.wait_for_timeout(500)
    raise RuntimeError(f"Não consegui preencher {seletor} com {esperado}.")


# ---- Impressão / PDF ----------------------------------------------------------------------

def aguardar_pagina_de_impressao(context, page, paginas_antes):
    """Após clicar em IMPRIMIR, devolve a página que contém o documento (nova aba ou a mesma)."""
    for _ in range(int(config.TIMEOUT_IMPRESSAO / 0.25)):
        novas = [p for p in context.pages if p not in paginas_antes]
        if novas:
            alvo = novas[-1]
            alvo.wait_for_load_state("load")
            return alvo
        page.wait_for_timeout(250)
    page.wait_for_load_state("load")
    return page


def salvar_pdf(context, pagina, caminho: Path) -> None:
    """Gera o PDF da página (equivale a Imprimir > Salvar como PDF) sem abrir o diálogo do Chrome."""
    try:
        sessao = context.new_cdp_session(pagina)
        resultado = sessao.send(
            "Page.printToPDF", {"printBackground": True, "preferCSSPageSize": True}
        )
        caminho.write_bytes(base64.b64decode(resultado["data"]))
    except Exception:  # noqa: BLE001
        log.warning("printToPDF via CDP falhou; tentando page.pdf().", exc_info=True)
        pagina.pdf(path=str(caminho), print_background=True)  # só funciona em Chromium sem interface


# ---- Diagnóstico --------------------------------------------------------------------------

def capturar_erro(context) -> list[Path]:
    """Salva uma captura de tela de cada aba aberta (melhor esforço) para ajudar a achar o erro."""
    salvos: list[Path] = []
    try:
        config.PASTA_ERROS.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        for i, aba in enumerate(context.pages):
            try:
                destino = config.PASTA_ERROS / f"{carimbo}_aba{i}.png"
                aba.screenshot(path=str(destino), timeout=5000)
                salvos.append(destino)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        log.debug("Falha ao capturar telas de erro.", exc_info=True)
    return salvos
