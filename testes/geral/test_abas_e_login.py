"""
Cada automação abre SÓ as abas dela, e DARE/BB pedem o login antes de começar.

    python -m pytest testes/geral/test_abas_e_login.py -q

- preparar_navegador.abrir_abas_sem_conectar: contra um Chrome falso (o /json dele) e
  contra o Chromium de verdade do Playwright (o "#" do endereço do BB chega inteiro).
- modulo_geral: login_estado / abrir_abas / login_confirmado (DARE e BB).
- app_janela: o Anexar no SEI e a NE abrem SIGEF e SEI, sem o BB.
- Cadastro: sem aba do SIGEF, usa uma aba vazia ou uma nova, nunca a de outro sistema.
"""
import builtins
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_abas_"))

from automacoes.sigef_sei import preparar_navegador as pn  # noqa: E402

URL_BB = pn.URL_BB_LOGIN


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ChromeFalso:
    """Só o /json do Chrome: lista as abas e abre uma nova (PUT /json/new?<url>)."""

    def __init__(self, abertas):
        self.abertas = list(abertas)
        self.novas, self.metodos = [], []
        falso = self

        class Tratador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self, corpo):
                dados = json.dumps(corpo).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                if self.path == "/json/list":
                    self._responder([{"type": "page", "url": u} for u in falso.abertas])
                else:
                    falso.metodos.append("GET")
                    self.send_error(405)

            def do_PUT(self):
                caminho, _, consulta = self.path.partition("?")
                url = urllib.parse.unquote(consulta)
                falso.metodos.append("PUT" if caminho == "/json/new" else "PUT " + caminho)
                falso.novas.append(url)
                falso.abertas.append(url)
                self._responder({"type": "page", "url": url})

        self.servidor = HTTPServer(("127.0.0.1", 0), Tratador)
        self.porta = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


class TestAbrirAbas(unittest.TestCase):
    def test_abre_so_as_que_faltam(self):
        chrome = ChromeFalso(["https://sei.sistemas.ro.gov.br/sei/controlador.php?acao=x", "about:blank"])
        self.addCleanup(chrome.fechar)
        abas = [(pn.DOMINIO_SEI, pn.URL_SEI), (pn.DOMINIO_BB, URL_BB)]
        pn.abrir_abas_sem_conectar(abas, porta=chrome.porta)
        self.assertEqual(chrome.novas, [URL_BB])  # o SEI já estava aberto; o "#" chegou inteiro
        self.assertEqual(chrome.metodos, ["PUT"])
        pn.abrir_abas_sem_conectar(abas, porta=chrome.porta)  # de novo: não duplica
        self.assertEqual(chrome.novas, [URL_BB])

    def test_chrome_fechado_abre_com_as_abas(self):
        with mock.patch.object(pn, "porta_ja_esta_em_uso", return_value=False), \
                mock.patch.object(pn, "abrir_chrome_debug") as abrir:
            pn.abrir_abas_sem_conectar([("dare.sefin.ro.gov.br", "https://dare.sefin.ro.gov.br/avulso")], porta=1)
        abrir.assert_called_once_with(1, urls=["https://dare.sefin.ro.gov.br/avulso"])

    def test_chromium_de_verdade(self):
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                executavel = pw.chromium.executable_path
        except Exception:  # noqa: BLE001
            self.skipTest("Sem o Chromium do Playwright")
        if not os.path.exists(executavel):
            self.skipTest("Sem o Chromium do Playwright")
        porta = _porta_livre()
        perfil = tempfile.mkdtemp(prefix="perfil_abas_")
        processo = subprocess.Popen(
            [executavel, "--headless=new", f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}",
             "--no-first-run", "--no-sandbox", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(processo.kill)
        fim = time.monotonic() + 20
        while not pn.porta_ja_esta_em_uso(porta) and time.monotonic() < fim:
            time.sleep(0.2)
        pagina = os.path.join(perfil, "aba.html")
        open(pagina, "w").close()
        url = "file://" + pagina + "?ambiente=X&segmento=est#/transacao/acesso-apj/1"

        def abertas():
            time.sleep(0.5)
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/list", timeout=5) as r:
                return [a["url"] for a in json.load(r) if a.get("type") == "page"]

        pn.abrir_abas_sem_conectar([("aba.html", url)], porta=porta)
        self.assertIn(url, abertas())
        pn.abrir_abas_sem_conectar([("aba.html", url)], porta=porta)  # já aberta: não duplica
        self.assertEqual(abertas().count(url), 1)


class TestLoginAntesDeComecar(unittest.TestCase):
    def setUp(self):
        from automacoes.dare import motor
        from janela import modulo_geral

        self.g, self.motor = modulo_geral, motor
        modulo_geral._confirmados.clear()
        antes = dict(motor._sessao)
        self.addCleanup(lambda: motor._sessao.update(antes))
        motor._sessao["login_confirmado"] = False

    def test_dare(self):
        with mock.patch.object(pn, "porta_ja_esta_em_uso", return_value=True), \
                mock.patch.object(pn, "abrir_abas_sem_conectar") as abrir:
            estado = self.g.chamar("login_estado", {"automacao": "dare"})
            self.assertEqual(estado, {"ok": True, "sistemas": ["DARE", "SEI"], "confirmado": False})
            self.assertEqual(self.g.chamar("abrir_abas", {"automacao": "dare"}), {"ok": True, "sistemas": ["DARE", "SEI"]})
            dominios = [d for d, _ in abrir.call_args.args[0]]
            self.assertEqual(dominios, ["dare.sefin.ro.gov.br", "sei.sistemas.ro.gov.br"])  # sem SIGEF e sem BB
            self.assertEqual(self.g.chamar("login_confirmado", {"automacao": "dare"}), {"ok": True})
            self.assertTrue(self.motor.login_ja_confirmado())  # não pergunta de novo no meio da execução
            self.assertTrue(self.g.chamar("login_estado", {"automacao": "dare"})["confirmado"])
        with mock.patch.object(pn, "porta_ja_esta_em_uso", return_value=False):  # Chrome fechado: pede de novo
            self.assertFalse(self.g.chamar("login_estado", {"automacao": "dare"})["confirmado"])

    def test_bb_e_erros(self):
        with mock.patch.object(pn, "abrir_abas_sem_conectar", side_effect=SystemExit("\nInstale o Chrome.\n")) as abrir:
            self.assertEqual(self.g.chamar("abrir_abas", {"automacao": "bb"}), {"ok": False, "erro": "Instale o Chrome."})
        self.assertEqual([d for d, _ in abrir.call_args.args[0]], [pn.DOMINIO_BB, pn.DOMINIO_SEI])
        with mock.patch.object(pn, "abrir_abas_sem_conectar", side_effect=OSError("recusada")):
            self.assertFalse(self.g.chamar("abrir_abas", {"automacao": "bb"})["ok"])

    def test_automacao_desconhecida(self):
        with self.assertRaises(ValueError):
            self.g.chamar("login_confirmado", {"automacao": "sei"})


class TestAbasDoAnexarNoSei(unittest.TestCase):
    def test_sem_banco_do_brasil(self):
        saida, erros, entrada = sys.stdout, sys.stderr, builtins.input
        import app_janela as A

        sys.stdout, sys.stderr, builtins.input = saida, erros, entrada
        t = A.Trabalhador()
        navegador = mock.Mock()
        navegador.is_connected.return_value = True
        with mock.patch.object(A, "conectar_chrome", return_value=(mock.Mock(), navegador, mock.Mock())), \
                mock.patch.object(A, "abrir_ou_reusar_aba") as abrir, mock.patch.object(A.ponte, "emitir"):
            t._conectar()
        self.assertEqual([c.args[1] for c in abrir.call_args_list], [pn.DOMINIO_SIGEF, pn.DOMINIO_SEI])


class TestAbaDoCadastro(unittest.TestCase):
    def _abrir(self, urls):
        from automacoes.cadastro import navegador as nav

        abas = [mock.Mock(url=u) for u in urls]
        for a in abas:
            a.is_closed.return_value = False
        nova = mock.Mock(url="about:blank")
        n = nav.Navegador(mock.Mock())
        n.browser = mock.Mock()
        n.browser.is_connected.return_value = True
        n.context = mock.Mock(pages=abas)
        n.context.new_page.return_value = nova
        n.abrir()
        return n, abas, nova

    def test_nao_toma_a_aba_do_sei(self):
        n, abas, nova = self._abrir(["https://sei.sistemas.ro.gov.br/sei/x"])
        self.assertIs(n.page, nova)
        abas[0].goto.assert_not_called()

    def test_usa_aba_vazia_ou_a_do_sigef(self):
        n, abas, _ = self._abrir(["https://sei.sistemas.ro.gov.br/x", "about:blank"])
        self.assertIs(n.page, abas[1])
        n, abas, _ = self._abrir(["https://sei.sistemas.ro.gov.br/x", "http://sigef.sefin.ro.gov.br/SIGEF2026/x"])
        self.assertIs(n.page, abas[1])


if __name__ == "__main__":
    unittest.main()
