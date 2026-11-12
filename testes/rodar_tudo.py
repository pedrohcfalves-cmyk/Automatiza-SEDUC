"""
Roda todos os testes do projeto com um comando só.

    python testes/rodar_tudo.py              todos os grupos
    python testes/rodar_tudo.py dare geral   só alguns

Termina com código 1 se algum grupo falhar (menos os de CONHECIDOS_QUEBRADOS).
Os testes rodam com LBA_PASTA_DADOS numa pasta temporária: nada toca os dados reais.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable]
PYTEST = PY + ["-m", "pytest", "-q", "-p", "no:cacheprovider"]

GRUPOS = {
    "divisao": PY + ["testes/testes_divisao.py"],
    "escolha": PY + ["testes/teste_escolha_documentos.py"],
    "dare": PY + ["-m", "unittest", "discover", "-s", "testes/dare", "-t", "."],
    "ne": PY + ["-m", "unittest", "discover", "-s", "testes/ne", "-t", "."],
    "geral": PY + ["-m", "unittest", "discover", "-s", "testes/geral", "-t", "."],
    "cache_janela": PY + ["-m", "unittest", "testes.teste_cache_janela"],
    "janela_demo": PY + ["testes/teste_janela_demo.py"],
    "ce_impressao_janela": PY + ["testes/teste_ce_impressao_janela.py"],
    "ce_impressao_navegador": PY + ["testes/teste_ce_impressao_navegador.py"],
    "ne_cenarios": PY + ["testes/ne/rodar_cenarios.py"],
    "anexar": PYTEST + ["testes/anexar"],      # ~10 min
    "cadastro": PYTEST + ["testes/cadastro"],  # só acha Chromium no Linux; no Windows os testes de navegador pulam
}

LIMITE_S = 30 * 60  # por grupo: travou = falhou

# nome -> motivo. Falha aqui aparece como "QUEBRADO (conhecido)" e não derruba o resultado.
CONHECIDOS_QUEBRADOS = {}


def _porta_9222_em_uso() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 9222), 0.5).close()
        return True
    except OSError:
        return False


def main(argv) -> int:
    nomes = argv or list(GRUPOS)
    desconhecidos = [n for n in nomes if n not in GRUPOS]
    if desconhecidos:
        print(f"Grupo desconhecido: {', '.join(desconhecidos)}. Existem: {', '.join(GRUPOS)}")
        return 2
    # testes/cadastro reaproveita qualquer Chrome na 9222: com o da automação aberto, mexeria nele.
    if _porta_9222_em_uso():
        print("A porta 9222 está respondendo: feche o Chrome da automação antes de rodar os testes.")
        return 2
    ambiente = dict(os.environ, LBA_PASTA_DADOS=tempfile.mkdtemp(prefix="testes_lba_"), PYTHONIOENCODING="utf-8")
    falhou = False
    for nome in nomes:
        inicio = time.time()
        try:
            r = subprocess.run(GRUPOS[nome], cwd=RAIZ, env=ambiente, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=LIMITE_S)
        except subprocess.TimeoutExpired as travou:
            r = subprocess.CompletedProcess(travou.cmd, 1, "", f"Travou: passou de {LIMITE_S // 60} min.")
        if r.returncode == 0:
            estado = "OK"
        elif nome in CONHECIDOS_QUEBRADOS:
            estado = f"QUEBRADO (conhecido: {CONHECIDOS_QUEBRADOS[nome]})"
        else:
            estado, falhou = "FALHOU", True
            print((r.stdout + r.stderr)[-3000:])
        print(f"{estado:8} {nome}  ({time.time() - inicio:.0f}s)", flush=True)
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
