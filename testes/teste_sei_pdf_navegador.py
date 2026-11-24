"""
O modo "Como salvar no SEI: Como PDF" num Chromium de verdade, contra uma
cópia da tela do SEI (os mesmos ids e eventos: Incluir Documento ->
" Externo" (escolher(-1)) -> #selSerie, #txtDataElaboracao, #optNato,
#optPublico, #filArquivo / .infraDivDropFile, #tblAnexos, #btnSalvar).

    python -m pytest testes/teste_sei_pdf_navegador.py -q

Confere: o tipo certo de cada documento (CE, NL, PP, OB normal e de
Regularização, NE), a data de hoje, Nato-digital, Público, o PDF enviado,
o número da PP/NE, a retomada (o que já foi salvo é pulado), o PDF
montado das imagens quando o original falta, o clique perdido no
"Incluir Documento", o campo de arquivo que não reage (vai por arrastar
e soltar), o arquivo recusado pelo SEI (nada criado, diagnóstico
gravado) e o Salvar que não responde (para sem repetir).

Precisa do Playwright com o Chromium dele e do pymupdf; sem eles, é pulado.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlparse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_sei_pdf_"))

try:
    import pymupdf
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PROC = "0029.001947/2026-67"
SEI = "https://sei.sistemas.ro.gov.br"
IMG = "data:image/gif;base64,R0lGODlhAQABAAAAACw="

# Um pedaço da lista #selSerie de verdade.
OPCOES = [
    ("null", "&nbsp;"), ("1050", "Despesa Certificada"), ("298", "NL - Nota de Lançamento"),
    ("982", "PP - Preparação de Pagamento"), ("314", "OB - Ordem Bancária de Regularização"),
    ("297", "Ordem Bancária"), ("294", "NE - Nota de Empenho"), ("83", "Declaração"),
]
COM_NUMERO = ["294", "982"]   # os tipos que, no SEI simulado, mostram o Número ao trocar o tipo

TIPOS = """<html><body><table>
<tr data-desc=" externo"><td><a href="#" onclick="escolher(-1)" tabindex="1003" class="ancoraOpcao"> Externo</a></td></tr>
<tr data-desc="despacho"><td><a href="#" onclick="escolher(5)" class="ancoraOpcao">Despacho</a></td></tr>
<tr data-desc="ob - ordem bancaria"><td><a href="#" onclick="escolher(313)" class="ancoraOpcao">OB - Ordem Bancária</a></td></tr>
</table><script>function escolher(n){ if(n==-1) location='/externo'; else location='/interno?s='+n; }</script></body></html>"""

FORM = """<html><body>
<select id="selSerie" name="selSerie" onchange="trocarSerie();" class="infraSelect">%OPCOES%</select>
<input type="text" id="txtDataElaboracao" name="txtDataElaboracao" onkeypress="return infraMascaraData(this, event)" class="infraText" value="">
<span id="divNumero" style="display:none"><input type="text" id="txtNumero" name="txtNumero"></span>
<input type="text" id="txtNomeArvore" name="txtNomeArvore" maxlength="50">
<input type="radio" name="rdoFormato" id="optNato" value="N" class="infraRadioInput" onclick="selecionarFormatoDigitalizado();"><label class="infraRadioLabel" for="optNato">Nato-digital</label>
<input type="radio" name="rdoFormato" id="optDigitalizado" value="D" class="infraRadioInput"><label class="infraRadioLabel" for="optDigitalizado">Digitalizado</label>
<input type="radio" name="rdoNivelAcesso" id="optRestrito" value="1" class="infraRadioInput"><label class="infraRadioLabel" for="optRestrito">Restrito</label>
<input type="radio" name="rdoNivelAcesso" id="optPublico" onchange="alterarNivelAcesso()" value="0" class="infraRadioInput"><label class="infraRadioLabel" for="optPublico">Público</label>
<form id="frmAnexos">
<input type="file" id="filArquivo" name="filArquivo" style="position:absolute;left:-9999px">
<div class="infraDivDropFile" style="width:300px;height:40px;border:1px dashed #888"></div>
<button id="btnUploadCancelarfrmAnexos" class="infraButton" style="display:none">Cancelar</button>
<input type="hidden" id="hdnAnexos" value="">
<table id="tblAnexos"><thead><tr><th>Nome</th><th>Tamanho</th></tr></thead><tbody></tbody></table>
</form>
<button type="button" onclick="confirmarDados()" accesskey="S" name="btnSalvar" id="btnSalvar" value="Salvar" class="infraButton"><span class="infraTeclaAtalho">S</span>alvar</button>
<script>
var CONFIG = %CONFIG%;
function infraMascaraData(){ return true; }
function selecionarFormatoDigitalizado(){}
function alterarNivelAcesso(){}
function trocarSerie(){ document.getElementById('divNumero').style.display = %COM_NUMERO%.indexOf(document.getElementById('selSerie').value) >= 0 ? '' : 'none'; }
var anexo = null;
function receber(arquivo){
  if (CONFIG.recusar_arquivo) { alert('Extensão de arquivo não permitida.'); return; }
  var cancelar = document.getElementById('btnUploadCancelarfrmAnexos');
  cancelar.style.display = 'block';
  var leitor = new FileReader();
  leitor.onload = function(){
    setTimeout(function(){
      anexo = {nome: arquivo.name, tamanho: arquivo.size, inicio: String.fromCharCode.apply(null, new Uint8Array(leitor.result.slice(0, 4)))};
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + arquivo.name + '</td><td>' + arquivo.size + '</td>';
      document.querySelector('#tblAnexos tbody').appendChild(tr);
      document.getElementById('hdnAnexos').value = arquivo.name;
      cancelar.style.display = 'none';
    }, 300);
  };
  leitor.readAsArrayBuffer(arquivo);
}
document.getElementById('filArquivo').addEventListener('change', function(){
  if (CONFIG.campo_mudo) return;            // o campo não reage: só o arrastar funciona
  if (this.files.length) receber(this.files[0]);
});
var area = document.querySelector('.infraDivDropFile');
area.addEventListener('dragover', function(e){ e.preventDefault(); });
area.addEventListener('drop', function(e){ e.preventDefault(); if (e.dataTransfer.files.length) receber(e.dataTransfer.files[0]); });
function marcado(nome){ var r = document.querySelector('input[name="' + nome + '"]:checked'); return r ? r.value : ''; }
function confirmarDados(){
  var serie = document.getElementById('selSerie').value;
  if (serie == 'null') { alert('Selecione o Tipo do Documento.'); return; }
  if (!document.getElementById('txtDataElaboracao').value) { alert('Informe a Data do Documento.'); return; }
  if (!marcado('rdoFormato')) { alert('Selecione o Formato.'); return; }
  if (!marcado('rdoNivelAcesso')) { alert('Selecione o Nível de Acesso.'); return; }
  if (!anexo) { alert('Nenhum arquivo informado.'); return; }
  if (CONFIG.salvar_mudo) return;           // o Salvar não responde
  if (CONFIG.recusar_salvar) { alert('Tipo de documento não liberado para esta unidade.'); return; }
  var dados = {serie: serie, data: document.getElementById('txtDataElaboracao').value,
    numero: document.getElementById('txtNumero').value, nome_arvore: document.getElementById('txtNomeArvore').value,
    formato: marcado('rdoFormato'), nivel: marcado('rdoNivelAcesso'), anexo: anexo};
  fetch('/salvar', {method: 'POST', body: JSON.stringify(dados)}).then(function(r){ return r.text(); }).then(function(id){
    window.parent.frames['ifrArvore'].location.reload();
    location = '/documento?id=' + id;
  });
}
</script></body></html>"""


def _pdf(caminho: str, paginas: int = 1, texto: str = "SIGEF") -> None:
    doc = pymupdf.open()
    for n in range(paginas):
        doc.new_page().insert_text((72, 72), f"{texto} pagina {n + 1}")
    doc.save(caminho)
    doc.close()


@unittest.skipIf(sync_playwright is None, "Playwright ou pymupdf não instalado")
class TestaModoPdfNoSei(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from automacoes.sigef_sei import etapa_listar_baixar as b
        from automacoes.sigef_sei import etapa_sei2, sei_pdf

        cls.b, cls.sei2, cls.pdf = b, etapa_sei2, sei_pdf
        cls._esperas = sei_pdf.ESPERAS_ENTRE_TENTATIVAS
        cls._inicio_upload = sei_pdf.TIMEOUT_INICIO_UPLOAD_S
        cls._salvar = sei_pdf.TIMEOUT_SALVAR_S
        sei_pdf.ESPERAS_ENTRE_TENTATIVAS = (0, 0)
        sei_pdf.TIMEOUT_INICIO_UPLOAD_S = 2
        cls.pw = sync_playwright().start()
        cls.navegador = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.pdf.ESPERAS_ENTRE_TENTATIVAS = cls._esperas
        cls.pdf.TIMEOUT_INICIO_UPLOAD_S = cls._inicio_upload
        cls.pdf.TIMEOUT_SALVAR_S = cls._salvar
        cls.navegador.close()
        cls.pw.stop()

    def setUp(self):
        self.pasta = os.path.join(self.b.PASTA_BASE, self.b.nome_pasta_valido(PROC))
        shutil.rmtree(self.pasta, ignore_errors=True)
        os.makedirs(self.pasta)
        shutil.rmtree(self.pdf.PASTA_DIAGNOSTICO_PDF, ignore_errors=True)
        self.salvos = []
        self.config = {"recusar_arquivo": False, "campo_mudo": False, "salvar_mudo": False, "recusar_salvar": False}
        self.perder_cliques = 0
        self.cliques_perdidos = 0
        self.ctx = self.navegador.new_context()
        self.ctx.route(f"{SEI}/**", self._servir)
        self.aba = self.ctx.new_page()
        self.aba.goto(f"{SEI}/controlador.php?acao=procedimento_trabalhar&infra_hash=abc")

    def tearDown(self):
        self.ctx.close()

    # ---- o SEI simulado ----

    def _servir(self, rota):
        url = urlparse(rota.request.url)
        q = parse_qs(url.query)

        def html(corpo):
            return rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)

        if url.path == "/controlador.php":
            return html(
                '<html><body><input id="txtPesquisaRapida">'
                '<iframe name="ifrArvore" src="/arvore" width=300 height=400></iframe>'
                '<iframe name="ifrVisualizacao" src="/visual" width=700 height=500></iframe></body></html>'
            )
        if url.path == "/arvore":
            docs = "".join(f"<div><a href='#'>{s['nome']} ({i + 1})</a></div>" for i, s in enumerate(self.salvos))
            return html(
                f"<html><body><a href='#' onclick=\"parent.frames['ifrVisualizacao'].location='/visual'\">{PROC}</a>"
                f"{docs}</body></html>"
            )
        if url.path == "/visual":
            perder = max(0, self.perder_cliques - self.cliques_perdidos)   # só os N primeiros cliques se perdem
            return html(
                f"<html><body><script>var perder = {perder};</script>"
                "<a href='#' onclick=\"if(perder > 0){perder--; fetch('/perdi'); return false} location='/tipos'; return false\">"
                f"<img title='Incluir Documento' src='{IMG}' width=20 height=20></a></body></html>"
            )
        if url.path == "/perdi":
            self.cliques_perdidos += 1
            return rota.fulfill(status=200, body="ok")
        if url.path == "/tipos":
            return html(TIPOS)
        if url.path == "/externo":
            opcoes = "".join(f'<option value="{v}">{t}</option>' for v, t in OPCOES)
            return html(
                FORM.replace("%OPCOES%", opcoes).replace("%CONFIG%", json.dumps(self.config))
                .replace("%COM_NUMERO%", json.dumps(COM_NUMERO))
            )
        if url.path == "/salvar":
            dados = json.loads(rota.request.post_data)
            dados["nome"] = dict(OPCOES)[dados["serie"]]
            self.salvos.append(dados)
            return rota.fulfill(status=200, body=str(len(self.salvos)))
        if url.path == "/documento":
            return html(f"<html><body>Documento {q.get('id', ['?'])[0]} (sem 'Incluir Documento' aqui)</body></html>")
        return rota.fulfill(status=404, body="")

    # ---- os arquivos da etapa anterior ----

    def baixado(self, nome: str, paginas: int = 1) -> list[str]:
        """Como o download faz: PDF temporário -> pdf_para_jpg (que guarda o .pdf ao lado)."""
        temp = os.path.join(self.pasta, "temp.pdf")
        _pdf(temp, paginas, nome)
        jpgs = self.b.pdf_para_jpg(temp, self.pasta, nome)
        os.remove(temp)
        return jpgs

    def pacote(self, so_ob: bool = False):
        ob = self.baixado("Ordem Bancária")
        if so_ob:
            return {"processo": PROC, "ob": "2026OB000777", "grupos_ce": [], "arquivos_ob": ob,
                    "lancamentos": [], "avisos_download": []}
        ce = self.baixado("Despesa Certificada - CE 2026CE000123")
        nl1 = self.baixado("Nota de Lançamento - PP 2026PP000001", paginas=2)
        nl2 = self.baixado("Nota de Lançamento - PP 2026PP000002")
        pp1 = self.baixado("Preparação de Pagamento - PP 2026PP000001")
        pp2 = self.baixado("Preparação de Pagamento - PP 2026PP000002")
        return {
            "processo": PROC, "ob": "2026OB000777",
            "grupos_ce": [("2026CE000123", ce)],
            "arquivos_ob": ob,
            "lancamentos": [
                {"pp": "2026PP000001", "arquivos_nl": nl1, "arquivos_pp": pp1, "numero_ce": "2026CE000123", "arquivos_ce": ce},
                {"pp": "2026PP000002", "arquivos_nl": nl2, "arquivos_pp": pp2, "numero_ce": "2026CE000123", "arquivos_ce": []},
            ],
            "avisos_download": [],
        }

    def rodar_ob(self, tipo_ob=None, dados=None):
        avisos = []
        self.sei2.executar_sei2(
            self.ctx, PROC, dados=dados or self.pacote(), tipo_ob=tipo_ob or self.sei2.TEXTO_LINK_OB_NORMAL,
            conferir_no_fim=False, avisos_saida=avisos, formato="pdf",
        )
        return avisos

    def relatorios(self) -> list[str]:
        pasta = self.pdf.PASTA_DIAGNOSTICO_PDF
        return sorted(n for n in os.listdir(pasta) if n.endswith(".txt")) if os.path.isdir(pasta) else []

    # ---- os testes ----

    def test_a_os_seis_documentos_da_ob_como_externo(self):
        self.perder_cliques = 1   # o 1º clique no "Incluir Documento" se perde (visto no BB)
        self.rodar_ob()
        self.assertEqual([s["serie"] for s in self.salvos], ["1050", "298", "298", "982", "982", "297"])
        hoje = time.strftime("%d/%m/%Y")
        for salvo in self.salvos:
            self.assertEqual((salvo["data"], salvo["formato"], salvo["nivel"]), (hoje, "N", "0"))
            self.assertEqual(salvo["anexo"]["inicio"], "%PDF")
        nomes = [s["anexo"]["nome"] for s in self.salvos]
        self.assertEqual(nomes[0], "Despesa Certificada - CE 2026CE000123.pdf")
        self.assertEqual(nomes[1], "Nota de Lançamento - PP 2026PP000001.pdf")   # 2 páginas: 1 PDF só
        self.assertEqual(nomes[5], "Ordem Bancária.pdf")
        self.assertEqual([s["numero"] for s in self.salvos[3:5]], ["000001", "000002"])   # Número da PP
        self.assertEqual(self.cliques_perdidos, 1)
        self.assertEqual(self.relatorios(), [])
        self.assertTrue(os.path.exists(self.pdf.ARQUIVO_DIAGNOSTICO_PDF))

    def test_b_ob_de_regularizacao_e_retomada_pula_o_que_ja_foi_salvo(self):
        from automacoes.geral import impressao_dos_arquivos

        dados = self.pacote()
        progresso = self.sei2.ProgressoSei(PROC, "2026OB000777")   # queda depois de 2 documentos
        progresso.marcar("CE 2026CE000123", "salvo", impressao=impressao_dos_arquivos(dados["grupos_ce"][0][1]))
        progresso.marcar("NL 2026PP000001", "salvo", impressao=impressao_dos_arquivos(dados["lancamentos"][0]["arquivos_nl"]))
        self.rodar_ob(self.sei2.TEXTO_LINK_OB_REGULARIZACAO, dados)
        self.assertEqual([s["serie"] for s in self.salvos], ["298", "982", "982", "314"])

    def test_c_pdf_original_ausente_e_montado_das_imagens(self):
        dados = self.pacote(so_ob=True)
        os.remove(os.path.join(self.pasta, "Ordem Bancária.pdf"))
        avisos = self.rodar_ob(dados=dados)
        self.assertEqual([s["serie"] for s in self.salvos], ["297"])
        self.assertEqual(self.salvos[0]["anexo"]["inicio"], "%PDF")
        self.assertTrue(any("montado com as imagens" in a for a in avisos), avisos)

    def test_d_campo_de_arquivo_mudo_vai_por_arrastar(self):
        self.config["campo_mudo"] = True
        self.rodar_ob(dados=self.pacote(so_ob=True))
        self.assertEqual([s["serie"] for s in self.salvos], ["297"])
        with open(self.pdf.ARQUIVO_DIAGNOSTICO_PDF, encoding="utf-8") as log:
            self.assertIn("arrastar e soltar", log.read())

    def test_e_arquivo_recusado_nao_cria_e_grava_diagnostico(self):
        self.config["recusar_arquivo"] = True
        with self.assertRaises(SystemExit) as erro:
            self.rodar_ob(dados=self.pacote(so_ob=True))
        mensagem = str(erro.exception.code)
        self.assertIn("Nada foi criado", mensagem)
        self.assertIn("Extensão de arquivo não permitida", mensagem)
        self.assertEqual(self.salvos, [])
        self.assertEqual(len(self.relatorios()), self.pdf.TENTATIVAS_ANTES_DE_SALVAR)
        with open(os.path.join(self.pdf.PASTA_DIAGNOSTICO_PDF, self.relatorios()[0]), encoding="utf-8") as arquivo:
            texto = arquivo.read()
        self.assertIn("Passo: enviar o PDF", texto)
        self.assertIn("1050  Despesa Certificada", texto)   # as opções do #selSerie vão no relatório

    def test_f_salvar_que_nao_responde_para_sem_repetir(self):
        self.config["salvar_mudo"] = True
        self.pdf.TIMEOUT_SALVAR_S = 2
        try:
            with self.assertRaises(SystemExit) as erro:
                self.rodar_ob(dados=self.pacote(so_ob=True))
        finally:
            self.pdf.TIMEOUT_SALVAR_S = self._salvar
        self.assertIn("PODE ter sido criado", str(erro.exception.code))
        self.assertEqual(len(self.relatorios()), 1)   # não tentou de novo: poderia duplicar
        with open(os.path.join(self.pasta, "progresso_sei.json"), encoding="utf-8") as arquivo:
            self.assertEqual(json.load(arquivo)["documentos"]["OB"]["estado"], "criando")

    def test_f2_salvar_recusado_nao_deixa_marca_de_criando(self):
        self.config["recusar_salvar"] = True
        with self.assertRaises(SystemExit) as erro:
            self.rodar_ob(dados=self.pacote(so_ob=True))
        mensagem = str(erro.exception.code)
        self.assertIn("Nada foi criado", mensagem)
        self.assertIn("não liberado para esta unidade", mensagem)
        self.assertEqual(self.salvos, [])
        with open(os.path.join(self.pasta, "progresso_sei.json"), encoding="utf-8") as arquivo:
            self.assertNotIn("OB", json.load(arquivo)["documentos"])   # a próxima rodada não avisa de duplicado

    def test_g_ne_como_pdf(self):
        from automacoes.ne import etapa as ne

        temp = os.path.join(self.pasta, "temp_ne.pdf")
        _pdf(temp, 2, "NE 000123")
        self.b.guardar_pdf(temp, self.pasta, "Nota de Empenho - NE 000123")
        arquivos = []
        with pymupdf.open(temp) as doc:
            for i, pagina in enumerate(doc, start=1):
                destino = os.path.join(self.pasta, f"Nota de Empenho - NE 000123_{i}.png")
                pagina.get_pixmap(dpi=50).save(destino)
                arquivos.append(destino)
        avisos = ne.anexar_ne(
            self.ctx, PROC, {"ne": "000123", "arquivos": arquivos, "avisos_download": []},
            "Empenho do contrato 12", formato="pdf",
        )
        self.assertEqual(avisos, [])
        self.assertEqual(len(self.salvos), 1)
        salvo = self.salvos[0]
        self.assertEqual((salvo["serie"], salvo["numero"], salvo["nome_arvore"]), ("294", "000123", "Empenho do contrato 12"))
        self.assertEqual(salvo["anexo"]["nome"], "Nota de Empenho - NE 000123.pdf")
        self.assertEqual((salvo["formato"], salvo["nivel"]), ("N", "0"))


class TestaNomesEFormato(unittest.TestCase):
    def test_nomes(self):
        from automacoes.sigef_sei import sei_pdf

        self.assertEqual(sei_pdf.candidatos_pdf(["/p/X_1.jpg", "/p/X_2.jpg"])[0], "/p/X.pdf")
        self.assertEqual(sei_pdf.candidatos_pdf(["/p/Ordem Bancária.jpg"])[0], "/p/Ordem Bancária.pdf")
        self.assertEqual(sei_pdf.normalizar_formato("PDF"), "pdf")
        self.assertEqual(sei_pdf.normalizar_formato(None), "imagem")
        self.assertEqual(sei_pdf.normalizar_formato("qualquer"), "imagem")


if __name__ == "__main__":
    unittest.main()
