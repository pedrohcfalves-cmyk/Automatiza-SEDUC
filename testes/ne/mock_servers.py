"""Mock mínimo de SIGEF (porta 8001, modo quirks, ids duplicados por caixa, popup que se fecha
sozinho depois do download) e SEI (porta 8002, pesquisa rápida + iframes) -- só para testar o script."""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import pymupdf

d = pymupdf.open()
for n in (1, 2):
    d.new_page().insert_text((72, 72), f"NOTA DE EMPENHO 2026NE000001 pagina {n}")
PDF = d.tobytes()

IMG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='30' height='30'%3E%3Crect width='30' height='30' fill='red'/%3E%3C/svg%3E"

SIGEF = f"""<html><body>
UG <input id="txtUnidadeGestora"> Gestao <input id="txtGestao_SIGEFPesquisa">
NE ini <input id="txtNotaEmpenhoNumeroInicial"> fim <input id="txtNotaEmpenhoNumeroFinal">
<a href="#" title="Gerar Relatório" id="btnImpressao_btnImprimir" onclick="window.open('/popup.html','_blank','width=400,height=300');return false"><img id="btnImpressao_BtnImprimir" src="{IMG}"></a>
</body></html>"""  # sem doctype => quirks, como o SIGEF real

HITS = {"pdf": 0}
LINK_PDF = "/nada" if os.environ.get("MOCK_BLOQUEADO") else "/ne.pdf"
TEM_NUMERO = os.environ.get("TEM_NUMERO") == "1"
RECARREGA = os.environ.get("MOCK_RECARREGA") == "1"   # recria o iframe do formulário ao marcar "Nenhum"

POPUP = f"""<html><body>
<a href="{LINK_PDF}" onclick="setTimeout(function(){{window.close()}},400)"><img border="0" alt="Imprime Arquivo Formato PostScript (.pdf)" src="{IMG}"></a>
</body></html>"""

SEI_HOME_FORM = """<form action="/controlador.php" method="get"><input type="hidden" name="acao" value="procedimento_trabalhar"><input id="txtPesquisaRapida" name="proc"></form>"""
SEI_HOME = """<html><body><form action="/controlador.php" method="get">
<input type="hidden" name="acao" value="procedimento_trabalhar">
<input id="txtPesquisaRapida" name="proc"></form></body></html>"""


def sei_processo(proc):
    return f"""<html><body>{SEI_HOME_FORM}
<iframe name="ifrArvore" src="/arvore?proc={proc}" width=300 height=300></iframe>
<iframe name="ifrVisualizacao" src="/visual" width=500 height=300></iframe></body></html>"""


VISUAL = f"""<html><body><img title="Incluir Documento" src="{IMG}" onclick="location='/tipos'"></body></html>"""
TIPOS = """<html><body>
<a href="#" onclick="escolher(293)" class="ancoraOpcao">NE - Nota de Empenho Especial</a><br>
<a href="#" onclick="escolher(294)" class="ancoraOpcao">NE - Nota de Empenho</a>
<script>function escolher(n){document.body.setAttribute('data-escolhido',n);location='/form?tipo='+n}</script></body></html>"""

FORM = f"""<html><body>
<input type="radio" id="optNenhum" name="m"><label class="infraRadioLabel" for="optNenhum">Nenhum</label>
{'<input id="txtNumero" name="numero">' if TEM_NUMERO else ('<input id="txtNumero" name="numero" readonly style="display:none">' if os.environ.get("TEM_NUMERO") == "2" else '')}
<input type="radio" id="optRestrito" name="n"><label class="infraRadioLabel" for="optRestrito">Restrito</label>
<select id="selHipoteseLegal"><option value="">-</option><option value="3">Documento Preparatorio</option></select>
<input type="text" id="txtNomeArvore" maxlength="50" name="txtNomeArvore" class="infraText" value="">
</body></html>"""


FORM_RECARREGA = FORM.replace("</body>", """<script>document.getElementById('optNenhum').addEventListener('click',function(){setTimeout(function(){
var p=window.parent,f=p.document.getElementsByName('ifrVisualizacao')[0],n=p.document.createElement('iframe');
n.name='ifrVisualizacao';n.src='/form?tipo=294&r=1';n.width=500;n.height=300;f.replaceWith(n)},30)})</script></body>""")


def handler(rotas):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            r = rotas(u.path, q)
            if r is None:
                self.send_response(404)
                self.end_headers()
                return
            corpo, tipo, extra = r
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo if isinstance(corpo, bytes) else corpo.encode())

    return H


HTML = "text/html; charset=utf-8"


def sigef(p, q):
    if p == "/sigef.html":
        return SIGEF, HTML, {}
    if p == "/popup.html":
        return POPUP, HTML, {}
    if p == "/__hits":
        return str(HITS["pdf"]), "text/plain", {}
    if p == "/nada":
        return "<html><body>sem download</body></html>", HTML, {}
    if p == "/ne.pdf":
        HITS["pdf"] += 1
        return PDF, "application/pdf", {"Content-Disposition": 'attachment; filename="rel.pdf"'}


def sei(p, q):
    if p == "/controlador.php":
        if q.get("acao") == ["procedimento_trabalhar"]:
            return sei_processo(q.get("proc", [""])[0]), HTML, {}
        return SEI_HOME, HTML, {}
    if p == "/arvore":
        return f"<html><body>Processo {q['proc'][0]}</body></html>", HTML, {}
    if p == "/visual":
        return VISUAL, HTML, {}
    if p == "/tipos":
        return TIPOS, HTML, {}
    if p == "/form":
        return (FORM_RECARREGA if RECARREGA and not q.get("r") else FORM), HTML, {}


if __name__ == "__main__":
    for porta, rotas in ((8001, sigef), (8002, sei)):
        threading.Thread(
            target=ThreadingHTTPServer(("127.0.0.1", porta), handler(rotas)).serve_forever, daemon=True
        ).start()
    threading.Event().wait()
