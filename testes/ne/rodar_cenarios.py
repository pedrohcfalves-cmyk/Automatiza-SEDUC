"""
Roda os cenários da NE contra o SIGEF e o SEI simulados, num Chromium sem tela.

    python testes/ne/rodar_cenarios.py           todos (A a F)
    python testes/ne/rodar_cenarios.py A D       só alguns

Precisa do Playwright com o Chromium dele (python -m playwright install chromium)
ou de CENARIOS_CHROME apontando para um Chrome. Usa as portas 8001/8002 (simulados)
e 9333 (Chromium dos testes): o Chrome da automação, na 9222, não é tocado.

    A  leitura da lista, download (popup que fecha sozinho), SEI, lote, métricas, relatório
    B  tipo NE sem o campo Número          C  download bloqueado pelo Chrome
    D  SEI recria o iframe do formulário   E  campo Número oculto/somente leitura
    F  tentativa anterior deixou um formulário aberto no processo
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA_CDP = "9333"
CENARIOS = ["A", "B", "C", "D", "E", "F"]

# O que cada cenário liga no simulado (mock_servers.py lê do ambiente).
AMBIENTE = {
    "A": {"TEM_NUMERO": "1"},
    "B": {"TEM_NUMERO": "0"},
    "C": {"MOCK_BLOQUEADO": "1"},
    "D": {"TEM_NUMERO": "1", "MOCK_RECARREGA": "1"},
    "E": {"TEM_NUMERO": "2"},
    "F": {"TEM_NUMERO": "1"},
}


def _chromium() -> str:
    if os.environ.get("CENARIOS_CHROME"):
        return os.environ["CENARIOS_CHROME"]
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        return p.chromium.executable_path


def _esperar_porta(porta: int, segundos: float = 30) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.2)
    return False


def rodar(cenario: str, chrome: str, pasta: str) -> bool:
    ambiente = {k: v for k, v in os.environ.items() if k not in ("TEM_NUMERO", "MOCK_BLOQUEADO", "MOCK_RECARREGA")}
    ambiente.update(AMBIENTE[cenario], CENARIOS_PORTA_CDP=PORTA_CDP, CENARIOS_PASTA=pasta)
    servidor = subprocess.Popen([sys.executable, os.path.join(AQUI, "mock_servers.py")], env=ambiente)
    navegador = subprocess.Popen(
        [chrome, "--headless=new", "--no-sandbox", f"--remote-debugging-port={PORTA_CDP}",
         f"--user-data-dir={os.path.join(pasta, 'chrome_' + cenario)}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not (_esperar_porta(8001) and _esperar_porta(8002) and _esperar_porta(int(PORTA_CDP))):
            print(f"FALHOU {cenario}: simulados ou Chromium não subiram")
            return False
        teste = subprocess.run([sys.executable, os.path.join(AQUI, "cenarios.py"), cenario], env=ambiente, timeout=300)
        return teste.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"FALHOU {cenario}: passou de 5 minutos")
        return False
    finally:
        for processo in (navegador, servidor):
            processo.terminate()
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()


def main() -> int:
    escolhidos = [c.upper() for c in sys.argv[1:]] or CENARIOS
    chrome = _chromium()
    pasta = tempfile.mkdtemp(prefix="cenarios_ne_")
    try:
        falhas = [c for c in escolhidos if not rodar(c, chrome, pasta)]
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    print("\nTODOS OS CENÁRIOS PASSARAM" if not falhas else f"\nCENÁRIOS COM FALHA: {' '.join(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
