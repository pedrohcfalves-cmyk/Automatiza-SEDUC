"""
A escolha "Como listar e imprimir a CE" (passo 3 do Anexar no SEI), da tela até o
comando da automação: a página clicada como um usuário, falando com o Python DE
VERDADE (Api do app_janela). Não abre SIGEF nem SEI: o trabalhador não é ligado,
o comando fica na fila e o teste confere o que chegaria em baixar_documentos.

    python testes/teste_ce_impressao_janela.py

Precisa do Playwright com o Chromium dele; sem ele, os testes são pulados.
"""
import builtins
import json
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "testes"))
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_ce_janela_"))

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

if sync_playwright:
    _saida, _erros, _input = sys.stdout, sys.stderr, builtins.input
    import app_janela as A  # noqa: E402
    sys.stdout, sys.stderr, builtins.input = _saida, _erros, _input
    from ponte_pagina import PaginaComPython  # noqa: E402
    from janela.reserva import RESERVA  # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright não instalado")
class TestaEscolhaDaCe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.pw.stop()

    def setUp(self):
        if os.path.exists(A.CAMINHO_CONFIG):
            os.remove(A.CAMINHO_CONFIG)
        self._esvaziar()
        self.p = PaginaComPython(self.pw, A)

    def tearDown(self):
        self.assertEqual(self.p.erros_js, [])
        self.p.fechar()

    def _esvaziar(self):
        RESERVA.liberar()  # sem Trabalhador rodando, ninguém libera a reserva do clique
        while not A.trabalhador.comandos.empty():
            A.trabalhador.comandos.get_nowait()

    def _passo3(self):
        self.p.page.evaluate("document.querySelectorAll('.tela').forEach(s => s.hidden = s.id !== 'tela-dados')")

    def _escolher(self, nome, valor):
        self.p.page.locator(f'input[name="{nome}"][value="{valor}"]').locator("xpath=..").click()

    def _marcado(self, nome):
        return self.p.page.evaluate(f"(document.querySelector('input[name=\"{nome}\"]:checked') || {{}}).value")

    def _comando(self):
        return self.p.esperar(lambda: None if A.trabalhador.comandos.empty() else A.trabalhador.comandos.get_nowait(),
                              segundos=10, mensagem="comando na fila do trabalhador")

    def _enviar_um(self):
        self.p.page.fill("#in-processo", "0029001947202667")
        self.p.page.fill("#in-ob", "2026OB136475")
        self._escolher("tipo-ob", "regularizacao")
        self.p.page.click("#btn-processar")
        return self._comando()

    def test_padrao_e_o_caminho_de_sempre(self):
        self._passo3()
        self.assertEqual(self._marcado("modo-ce"), "pp")
        self.assertEqual(self._marcado("modo-ce-lote"), "pp")
        nome, args = self._enviar_um()
        self.assertEqual(nome, "processar")
        self.assertIs(args["ce_impressao"], False)
        self.assertEqual(args["documentos"], ["CE", "NL", "PP", "OB"])

    def test_fica_logo_acima_de_como_a_ob_entra_no_sei(self):
        anterior = self.p.page.evaluate(
            "document.getElementById('campo-tipo').previousElementSibling.querySelector('legend').textContent"
        )
        self.assertEqual(anterior, "Como listar e imprimir a CE")

    def test_impressao_chega_na_automacao_e_e_lembrada(self):
        self._passo3()
        self._escolher("modo-ce", "impressao")
        self.assertEqual(self._marcado("modo-ce-lote"), "impressao")  # as duas abas andam juntas
        nome, args = self._enviar_um()
        self.assertEqual(nome, "processar")
        self.assertIs(args["ce_impressao"], True)
        self.p.esperar(lambda: "CE pela tela de impressão" in self.p.texto("#exec-docs"), mensagem="exec-docs")
        with open(A.CAMINHO_CONFIG, encoding="utf-8") as arq:
            self.assertEqual(json.load(arq)["modo_ce"], "impressao")

        # Abrindo de novo, a escolha volta.
        self.p.fechar()
        self.p = PaginaComPython(self.pw, A)
        self.p.esperar(lambda: self._marcado("modo-ce") == "impressao", mensagem="escolha lembrada")

    def test_lote_leva_a_escolha(self):
        self._passo3()
        self.p.page.click("#aba-lote")
        self._escolher("modo-ce-lote", "impressao")
        self.assertEqual(self._marcado("modo-ce"), "impressao")
        self.p.page.fill("#in-lista", "0029.001947/2026-67\t2026OB136475\tRegularização")
        self.p.page.dispatch_event("#in-lista", "input")
        self.p.esperar("!document.getElementById('btn-lote').disabled", mensagem="lista conferida")
        self.p.page.click("#btn-lote")
        nome, args = self._comando()
        self.assertEqual(nome, "lote")
        self.assertIs(args["ce_impressao"], True)
        self.assertEqual(len(args["itens"]), 1)

    def test_automacao_em_andamento_avisa_e_nao_enfileira_de_novo(self):
        self._passo3()
        RESERVA.tentar()  # já há uma OB na fila (clique anterior)
        self.p.page.fill("#in-processo", "0029001947202667")
        self.p.page.fill("#in-ob", "2026OB136475")
        self._escolher("tipo-ob", "regularizacao")
        self.p.page.click("#btn-processar")
        self.p.esperar("!document.getElementById('dados-erro').hidden", segundos=5, mensagem="aviso na tela")
        self.assertIn("Já há uma automação em andamento", self.p.texto("#dados-erro"))
        self.assertTrue(A.trabalhador.comandos.empty())
        self.assertTrue(self.p.page.is_visible("#tela-dados"))

    def test_lote_com_automacao_em_andamento_avisa(self):
        self._passo3()
        self.p.page.click("#aba-lote")
        self.p.page.fill("#in-lista", "0029.001947/2026-67\t2026OB136475\tRegularização")
        self.p.page.dispatch_event("#in-lista", "input")
        self.p.esperar("!document.getElementById('btn-lote').disabled", mensagem="lista conferida")
        RESERVA.tentar()
        self.p.page.click("#btn-lote")
        self.p.esperar("!document.getElementById('lote-erro-leitura').hidden", segundos=5, mensagem="aviso na tela")
        self.assertIn("Já há uma automação em andamento", self.p.texto("#lote-erro-leitura"))
        self.assertTrue(A.trabalhador.comandos.empty())

    def test_api_aceita_janela_antiga_e_valor_estranho(self):
        api = A.Api()
        r = api.processar("0029001947202667", "136475", "regularizacao", ["CE"])  # sem modo_ce
        self.assertTrue(r["ok"])
        self.assertIs(self._comando()[1]["ce_impressao"], False)
        RESERVA.liberar()
        r = api.processar("0029001947202667", "136475", "regularizacao", ["CE"], "qualquer")
        self.assertEqual(r["modo_ce"], "pp")
        self.assertIs(self._comando()[1]["ce_impressao"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
