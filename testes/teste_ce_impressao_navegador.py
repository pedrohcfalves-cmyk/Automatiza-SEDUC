"""
A CE pela tela "Imprimir Despesa Certificada" num Chromium de verdade, contra uma
cópia da tela do SIGEF (os mesmos campos, ids e eventos do HTML real): preenche,
clica no Imprimir, escolhe o PDF na janela de formato, baixa e converte em JPG.
Confere também o diagnóstico (foto, HTML e relatório) quando a tela muda.

    python testes/teste_ce_impressao_navegador.py

Precisa do Playwright com o Chromium dele e do pymupdf; sem eles, é pulado.
"""
import os
import shutil
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_ce_nav_"))

try:
    import pymupdf
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# Os três campos copiados do SIGEF (com os eventos), mais o Imprimir padrão.
TELA_CE = """<html><head><script>
function AutoTabular(){} function FormatarValorNumerico(){return true} function RemoverZerosEsquerda(){}
function ValidarDigito(){return true} function LimparToolTip(){} function LimparValorHidden(){}
function PesquisarLimparToolTip(){} function FormatarValorZerosEsquerda(){return true} function RemoverMascara(){}
function imprimir(){
  var q = 'ug=' + document.getElementById('txtCdUnidadeGestora').value
        + '&g=' + document.getElementById('txtCdGestao_SIGEFPesquisa').value
        + '&ce=' + document.getElementById('txtDespesaCertificadaNumero_SIGEFPesquisa').value;
  window.open('Formato.aspx?' + q, 'formato'); return false;
}
</script></head><body>
<input name="txtCdUnidadeGestora" type="text" maxlength="6" id="txtCdUnidadeGestora" class="SIGEFTextBox" onkeyup="AutoTabular(this,6,event);" onpaste="javascript: return false;" onblur="javascript: return FormatarValorNumerico(this, event, '999999');" onfocus="javascript:RemoverZerosEsquerda(this, event, '999999');" onkeypress="javascript: return ValidarDigito(this, event, '999999');" onkeydown="javascript:LimparToolTip('txtCdUnidadeGestora', event);LimparValorHidden('txtCdUnidadeGestora_hdn_tooltip');" style="width:47px;text-align:right;">
<input name="txtCdGestao$SIGEFPesquisa" type="text" maxlength="5" id="txtCdGestao_SIGEFPesquisa" class="SIGEFPesquisa" onpaste="javascript: return false;" onblur="javascript: return FormatarValorNumerico(this, event, '99999');" onkeypress="javascript: return ValidarDigito(this, event, '99999');" onfocus="javascript:RemoverZerosEsquerda(this, event, '99999');" onkeydown="javascript:PesquisarLimparToolTip('txtCdGestao_SIGEFPesquisa', 'txtCdGestao_hdn_tooltip', event);" style="color:Black;width:59px;text-align:left;">
<input name="txtDespesaCertificadaNumero$SIGEFPesquisa" type="text" maxlength="6" id="txtDespesaCertificadaNumero_SIGEFPesquisa" class="SIGEFPesquisa" onpaste="javascript: return false;" onblur="javascript: return FormatarValorZerosEsquerda(this, event, '999999');" onkeypress="javascript: return ValidarDigito(this, event, '999999');" onfocus="javascript:RemoverMascara(this, event, '999999');" onkeydown="javascript:PesquisarLimparToolTip('txtDespesaCertificadaNumero_SIGEFPesquisa', 'txtDespesaCertificadaNumero_hdn_tooltip', event);" style="color:Black;width:59px;text-align:right;" title="">
%IMPRIMIR%
</body></html>"""
IMPRIMIR = ('<a id="btnBotoesImpressao_btnImprimir" title="Gerar Relatório" href="#" onclick="return imprimir()">'
            '<img id="btnBotoesImpressao_BtnImprimir" src="x.gif"></a>')
FORMATO = '<html><body><a href="Pdf.aspx?{q}"><img alt="Imprime Arquivo Formato PostScript (.pdf)" src="p.gif"></a></body></html>'


def _pdf(texto: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), texto)
    dados = doc.tobytes()
    doc.close()
    return dados


@unittest.skipIf(sync_playwright is None, "Playwright ou pymupdf não instalado")
class TestaTelaDeImpressaoDaCe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from automacoes.sigef_sei import etapa_listar_baixar as b

        cls.b = b
        cls._ano = b.ano_sigef
        b.ano_sigef = lambda: 2026
        cls.pw = sync_playwright().start()
        cls.navegador = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.b.ano_sigef = cls._ano
        cls.navegador.close()
        cls.pw.stop()

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="ce_")
        self.pedidos = []          # parâmetros que chegaram ao "SIGEF" no PDF
        self.tela = TELA_CE.replace("%IMPRIMIR%", IMPRIMIR)
        self.texto_pdf = "DESPESA CERTIFICADA 2026CE{ce}"
        self.ctx = self.navegador.new_context(accept_downloads=True)
        self.ctx.route("http://sigef.sefin.ro.gov.br/**", self._servir)
        self.aba = self.ctx.new_page()

    def tearDown(self):
        self.ctx.close()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def _servir(self, rota):
        url = urlparse(rota.request.url)
        q = parse_qs(url.query)
        if "FINImprimirDespesaCertificadaSituacao" in url.path:
            return rota.fulfill(body=self.tela, content_type="text/html; charset=utf-8")
        if url.path.endswith("Formato.aspx"):
            return rota.fulfill(body=FORMATO.format(q=url.query), content_type="text/html")
        if url.path.endswith("Pdf.aspx"):
            self.pedidos.append({k: v[0] if v else "" for k, v in q.items()})
            ce = (q.get("ce") or [""])[0]
            return rota.fulfill(body=_pdf(self.texto_pdf.format(ce=ce)), content_type="application/pdf",
                                headers={"Content-Disposition": "attachment; filename=ce.pdf"})
        return rota.fulfill(body="")

    def test_baixa_a_ce_com_os_campos_certos(self):
        jpgs, conferida = self.b._baixar_ce_impressao(self.ctx, self.aba, self.pasta, "2026CE000123", "000123")
        self.assertEqual(self.pedidos, [{"ug": "160001", "g": "1", "ce": "000123"}])
        self.assertEqual(len(jpgs), 1)
        self.assertTrue(os.path.getsize(jpgs[0]) > 0)
        self.assertTrue(jpgs[0].endswith("Despesa Certificada - CE 2026CE000123.jpg"))
        self.assertIs(conferida, True)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "temp_ce.pdf")))
        self.assertEqual(len(self.ctx.pages), 1)   # a janela de formato foi fechada

    def test_pdf_com_outra_ce_vira_aviso(self):
        self.texto_pdf = "DESPESA CERTIFICADA 2026CE999999"
        lanc = [{"numero_ce": "2026CE000123", "arquivos_ce": [], "arquivos_nl": [], "arquivos_pp": []}]
        grupos, avisos = [], []
        self.b._baixar_ces_pela_impressao(self.ctx, self.aba, self.pasta, [("2026CE000123", "000123")],
                                          lanc, grupos, avisos)
        self.assertEqual(len(grupos), 1)               # anexa, mas avisa na conferência
        self.assertEqual(lanc[0]["arquivos_ce"], grupos[0][1])
        self.assertEqual(len(avisos), 1)
        self.assertIn("não mostra o número 000123", avisos[0])

    def test_tela_mudou_pula_a_ce_e_grava_diagnostico(self):
        self.tela = TELA_CE.replace("%IMPRIMIR%", "")   # sem o Imprimir
        guardado, self.b.TIMEOUT_CE_MS = self.b.TIMEOUT_CE_MS, 1500
        try:
            antes = set(os.listdir(self.b.PASTA_DIAGNOSTICO_CE)) if os.path.isdir(self.b.PASTA_DIAGNOSTICO_CE) else set()
            lanc = [{"numero_ce": "2026CE000123", "arquivos_ce": [], "arquivos_nl": [], "arquivos_pp": []}]
            grupos, avisos = [], []
            self.b._baixar_ces_pela_impressao(self.ctx, self.aba, self.pasta, [("2026CE000123", "000123")],
                                              lanc, grupos, avisos)
        finally:
            self.b.TIMEOUT_CE_MS = guardado
        self.assertEqual(grupos, [])
        self.assertEqual(lanc[0]["arquivos_ce"], [])
        self.assertIn("NÃO foi anexada", avisos[0])
        novos = sorted(set(os.listdir(self.b.PASTA_DIAGNOSTICO_CE)) - antes)
        self.assertEqual([os.path.splitext(n)[1] for n in novos], [".html", ".png", ".txt"])
        relatorio = open(os.path.join(self.b.PASTA_DIAGNOSTICO_CE, novos[-1]), encoding="utf-8").read()
        self.assertIn("clicar em Imprimir", relatorio)
        self.assertRegex(relatorio, r'Imprimir\s+a\[title="Gerar Relatório"\]\s+0')
        self.assertRegex(relatorio, r"Número da CE\s+#txtDespesaCertificadaNumero_SIGEFPesquisa\s+1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
