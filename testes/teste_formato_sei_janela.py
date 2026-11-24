"""
A escolha "Como salvar no SEI" (Como imagem / Como PDF), no passo 3 do Anexar
no SEI e da Nota de Empenho, da tela até o comando da automação: a página
clicada como um usuário, falando com o Python DE VERDADE (Api do app_janela).
Não abre SIGEF nem SEI: o trabalhador não é ligado, o comando fica na fila e
o teste confere o que chegaria em executar_sei2 / processar_ne.

    python -m pytest testes/teste_formato_sei_janela.py -q

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
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_formato_janela_"))

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
class TestaComoSalvarNoSei(unittest.TestCase):
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
        RESERVA.liberar()
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

    def _config(self) -> dict:
        with open(A.CAMINHO_CONFIG, encoding="utf-8") as arq:
            return json.load(arq)

    # ---- Anexar no SEI (OB) ----

    def test_padrao_e_imagem(self):
        self._passo3()
        self.assertEqual(self._marcado("formato-sei"), "imagem")
        self.assertEqual(self._marcado("formato-sei-lote"), "imagem")

    def test_pdf_chega_na_automacao_e_e_lembrado(self):
        self._passo3()
        self._escolher("formato-sei", "pdf")
        self.assertEqual(self._marcado("formato-sei-lote"), "pdf")   # as duas abas andam juntas
        self.p.page.fill("#in-processo", "0029001947202667")
        self.p.page.fill("#in-ob", "2026OB136475")
        self._escolher("tipo-ob", "ordem_bancaria")
        self.p.page.click("#btn-processar")
        nome, args = self._comando()
        self.assertEqual(nome, "processar")
        self.assertEqual(args["formato"], "pdf")
        self.assertEqual(args["tipo_ob"], "OB - Ordem Bancária")
        self.p.esperar(lambda: "como PDF (Externo)" in self.p.texto("#exec-docs"), mensagem="exec-docs")
        self.assertEqual(self._config()["formato_sei"], "pdf")

        self.p.fechar()   # abrindo de novo, a escolha volta
        self.p = PaginaComPython(self.pw, A)
        self.p.esperar(lambda: self._marcado("formato-sei") == "pdf", mensagem="escolha lembrada")

    def test_lote_leva_a_escolha(self):
        self._passo3()
        self.p.page.click("#aba-lote")
        self._escolher("formato-sei-lote", "pdf")
        self.assertEqual(self._marcado("formato-sei"), "pdf")
        self.p.page.fill("#in-lista", "0029.001947/2026-67\t2026OB136475\tRegularização")
        self.p.page.dispatch_event("#in-lista", "input")
        self.p.esperar("!document.getElementById('btn-lote').disabled", mensagem="lista conferida")
        self.p.page.click("#btn-lote")
        nome, args = self._comando()
        self.assertEqual(nome, "lote")
        self.assertEqual(args["formato"], "pdf")

    def test_api_aceita_janela_antiga_e_valor_estranho(self):
        api = A.Api()
        r = api.processar("0029001947202667", "136475", "regularizacao", ["CE"])   # sem formato_sei
        self.assertEqual(r["formato_sei"], "imagem")
        self.assertEqual(self._comando()[1]["formato"], "imagem")
        RESERVA.liberar()
        r = api.processar("0029001947202667", "136475", "regularizacao", ["CE"], "pp", "qualquer")
        self.assertEqual(r["formato_sei"], "imagem")

    # ---- Nota de Empenho ----

    def _ne_passo3(self):
        self.p.page.click('.modulo[data-modulo="ne"]')
        self.p.page.wait_for_selector("#tela-ne:not([hidden])")
        self.p.page.evaluate(
            "document.querySelectorAll('.ne-passo').forEach(p => p.hidden = p.id !== 'ne-p-dados')"
        )

    def test_ne_pdf_chega_na_automacao_e_e_lembrado(self):
        self._ne_passo3()
        self.assertEqual(self._marcado("ne-formato-sei"), "imagem")
        self._escolher("ne-formato-sei", "pdf")
        self.assertEqual(self._marcado("ne-formato-sei-lote"), "pdf")
        self.p.page.fill("#ne-in-processo", "0029001947202667")
        self.p.page.fill("#ne-in-ne", "2026NE000123")
        self.p.page.click("#ne-btn-processar")
        nome, args = self._comando()
        self.assertEqual(nome, "ne_processar")
        self.assertEqual(args["formato"], "pdf")
        self.assertEqual(self._config()["formato_sei_ne"], "pdf")
        self.assertNotIn("formato_sei", self._config())   # a OB tem a escolha dela

    def test_ne_lote_leva_a_escolha(self):
        self._ne_passo3()
        self.p.page.click("#ne-aba-lote")
        self._escolher("ne-formato-sei-lote", "pdf")
        self.p.page.fill("#ne-in-lista", "0029.001947/2026-67\t2026NE000123")
        self.p.page.dispatch_event("#ne-in-lista", "input")
        self.p.esperar("!document.getElementById('ne-btn-lote').disabled", mensagem="lista conferida")
        self.p.page.click("#ne-btn-lote")
        nome, args = self._comando()
        self.assertEqual(nome, "ne_lote")
        self.assertEqual(args["formato"], "pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
