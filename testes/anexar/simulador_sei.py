"""
SEI SIMULADO para os testes -- só o que a Etapa SEI (2) (etapa_sei2.py)
usa, servido pelo próprio Playwright (context.route), sem rede.

    controle de processos   #txtPesquisaRapida (Enter pesquisa)
    processo aberto         frames ifrArvore (árvore) e ifrVisualizacao
    ifrVisualizacao         img[title="Incluir Documento"]
                            -> a.ancoraOpcao (tipo do documento)
                            -> label.infraRadioLabel[for=optNenhum/optRestrito],
                               #txtNumero, #selHipoteseLegal, #btnSalvar (2x, como no SEI)
                            -> abre o EDITOR numa janela nova
    editor                  CKEditor 4 de verdade (testes/vendor/ckeditor4) com:
                              - plugin "base64image": diálogo "Imagem" com o campo
                                de arquivo filArquivo dentro de
                                iframe.cke_dialog_ui_input_file (igual ao SEI);
                              - botão Salvar (a.cke_button__save, title "Salvar"),
                                que grava o HTML no "servidor" -- recarregar a
                                página mostra o que foi gravado de verdade.

O "servidor" recusa documento acima de `limite_bytes` com a mesma mensagem
do SEI ("não pode exceder 2MB. Utilize a opção Documento Externo") e pode
simular falhas de gravação (internet caindo) com `falhas_salvar`.
"""
import html
import mimetypes
import os
import re
from urllib.parse import parse_qs, urlparse

PASTA_CKEDITOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "ckeditor4")
TIPOS = [
    "Despesa Certificada",
    "NL - Nota de Lançamento",
    "PP - Preparação de Pagamento",
    "OB - Ordem Bancária de Regularização",
    "OB - Ordem Bancária",
]
MENSAGEM_TAMANHO = "O documento com imagem não pode exceder 2MB. Utilize a opção Documento Externo."
IMG_1PX = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"


def _pagina(titulo: str, corpo: str, head: str = "") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(titulo)}</title>{head}</head><body>{corpo}</body></html>"
    )


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


class SeiSimulado:
    def __init__(self, processo: str, limite_bytes: int = 2_000_000, falhas_salvar: dict = None):
        self.processo = processo
        self.limite_bytes = limite_bytes
        # {número do documento (1, 2, ...): quantas vezes o Salvar falha}
        self.falhas_salvar = dict(falhas_salvar or {})
        self.documentos: list[dict] = []
        self._por_token: dict[str, dict] = {}

    # ------------------------------------------------------------ roteamento

    def instalar(self, context) -> None:
        context.route(re.compile(r"https://sei\.sistemas\.ro\.gov\.br/.*"), self._atender)

    def _html(self, route, corpo: str, status: int = 200) -> None:
        route.fulfill(status=status, content_type="text/html; charset=utf-8", body=corpo)

    def _atender(self, route, request) -> None:
        url = urlparse(request.url)
        if url.path.startswith("/ckeditor/"):
            return self._arquivo_ckeditor(route, url.path[len("/ckeditor/"):])

        q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        acao = q.get("acao", "procedimento_controlar")

        if acao == "procedimento_controlar":
            return self._html(route, self._controle())
        if acao == "procedimento_trabalhar":
            return self._html(route, self._processo(q))
        if acao == "arvore":
            return self._html(route, self._arvore())
        if acao == "visualizar":
            return self._html(route, self._visualizar())
        if acao == "documento_escolher_tipo":
            return self._html(route, self._escolher_tipo())
        if acao == "documento_cadastrar":
            return self._html(route, self._cadastrar(q))
        if acao == "editor_montar":
            return self._html(route, self._editor(q))
        if acao == "editor_salvar":
            return self._salvar(route, request, q)
        return self._html(route, _pagina("SEI", "<p>?</p>"), status=404)

    def _arquivo_ckeditor(self, route, relativo: str) -> None:
        caminho = os.path.normpath(os.path.join(PASTA_CKEDITOR, relativo))
        if not caminho.startswith(PASTA_CKEDITOR) or not os.path.isfile(caminho):
            return route.fulfill(status=404, body="")
        tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
        with open(caminho, "rb") as arquivo:
            route.fulfill(status=200, headers={"Content-Type": tipo}, body=arquivo.read())

    # ------------------------------------------------------------ telas

    def _pesquisa(self) -> str:
        return (
            "<form method='get' action='controlador.php'>"
            "<input type='hidden' name='acao' value='procedimento_trabalhar'>"
            "<input id='txtPesquisaRapida' name='q'></form>"
        )

    def _controle(self) -> str:
        return _pagina("SEI - Controle de Processos", self._pesquisa() + "<p>Controle de Processos</p>")

    def _processo(self, q: dict) -> str:
        if _so_digitos(q.get("q", "")) != _so_digitos(self.processo):
            return _pagina("SEI - Pesquisa", self._pesquisa() + "<p>Nenhum resultado.</p>")
        return _pagina(
            "SEI - Processo",
            self._pesquisa()
            + "<iframe name='ifrArvore' id='ifrArvore' src='controlador.php?acao=arvore' width='300' height='400'></iframe>"
            + "<iframe name='ifrVisualizacao' id='ifrVisualizacao' src='controlador.php?acao=visualizar' width='700' height='600'></iframe>",
        )

    def _arvore(self) -> str:
        itens = "".join(f"<li>{html.escape(d['tipo'])} {html.escape(d['numero'])}</li>" for d in self.documentos)
        return _pagina("Árvore", f"<p>{html.escape(self.processo)}</p><ul>{itens}</ul>")

    def _visualizar(self) -> str:
        return _pagina(
            "Visualização",
            f"<img title='Incluir Documento' src='{IMG_1PX}' style='width:24px;height:24px;cursor:pointer' "
            "onclick=\"location.href='controlador.php?acao=documento_escolher_tipo'\">",
        )

    def _escolher_tipo(self) -> str:
        links = "".join(
            f"<p><a class='ancoraOpcao' href='controlador.php?acao=documento_cadastrar&tipo={i}'>{html.escape(t)}</a></p>"
            for i, t in enumerate(TIPOS)
        )
        return _pagina("Escolha o tipo", links)

    def _cadastrar(self, q: dict) -> str:
        tipo = TIPOS[int(q.get("tipo", "0"))]
        botao = "<button type='button' id='btnSalvar' onclick='salvar()'>Salvar</button>"
        corpo = (
            f"{botao}<h3>{html.escape(tipo)}</h3>"
            "<input type='radio' id='optModelo' name='texto' value='M'><label class='infraRadioLabel' for='optModelo'>Modelo</label>"
            "<input type='radio' id='optNenhum' name='texto' value='N'><label class='infraRadioLabel' for='optNenhum'>Nenhum</label>"
            "<p>Número: <input id='txtNumero'></p>"
            "<input type='radio' id='optPublico' name='nivel' value='publico' onclick='hip(false)'><label class='infraRadioLabel' for='optPublico'>Público</label>"
            "<input type='radio' id='optRestrito' name='nivel' value='restrito' onclick='hip(true)'><label class='infraRadioLabel' for='optRestrito'>Restrito</label>"
            "<select id='selHipoteseLegal' style='display:none'><option value=''></option>"
            "<option value='1'>Informação Pessoal</option><option value='3'>Documento Preparatório</option></select>"
            f"<br>{botao}"
            "<script>"
            "function hip(m){document.getElementById('selHipoteseLegal').style.display=m?'inline':'none';}"
            "function salvar(){"
            " var p=new URLSearchParams();"
            " p.set('acao','editor_montar');p.set('criar','1');"
            " p.set('token',Date.now()+'_'+Math.random());"
            f" p.set('tipo','{int(q.get('tipo', '0'))}');"
            " p.set('numero',document.getElementById('txtNumero').value);"
            " var n=document.querySelector('input[name=nivel]:checked');p.set('nivel',n?n.value:'');"
            " var t=document.querySelector('input[name=texto]:checked');p.set('texto',t?t.value:'');"
            " p.set('hip',document.getElementById('selHipoteseLegal').value);"
            " window.open('controlador.php?'+p.toString(),'_blank');"
            " location.href='controlador.php?acao=visualizar';}"
            "</script>"
        )
        return _pagina("Incluir Documento", corpo)

    def _editor(self, q: dict) -> str:
        if q.get("criar"):
            doc = self._por_token.get(q["token"])
            if doc is None:
                doc = {
                    "id": len(self.documentos) + 1,
                    "tipo": TIPOS[int(q.get("tipo", "0"))],
                    "numero": q.get("numero", ""),
                    "nivel": q.get("nivel", ""),
                    "texto_inicial": q.get("texto", ""),
                    "hipotese": q.get("hip", ""),
                    "html": "<p>Modelo padrão do documento -- deve ser apagado.</p>",
                    "salvamentos": 0,
                }
                self.documentos.append(doc)
                self._por_token[q["token"]] = doc
        else:
            doc = self.documentos[int(q.get("id_documento", "0")) - 1]

        id_doc = doc["id"]
        script = f"""
CKEDITOR.plugins.add('base64image', {{ init: function (editor) {{
  editor.addCommand('base64image', new CKEDITOR.dialogCommand('base64imageDialog'));
  editor.ui.addButton('base64image', {{ label: 'Imagem', command: 'base64image' }});
  CKEDITOR.dialog.add('base64imageDialog', function (editor) {{ return {{
    title: 'Imagem', minWidth: 300, minHeight: 80,
    contents: [{{ id: 'tab', label: 'Imagem', elements: [{{ type: 'file', id: 'filArquivo', label: 'Arquivo' }}] }}],
    onOk: function () {{
      var input = this.getContentElement('tab', 'filArquivo').getInputElement().$;
      var arquivo = input.files && input.files[0];
      if (!arquivo) return;
      var leitor = new FileReader();
      leitor.onload = function () {{ editor.insertHtml('<p><img src="' + leitor.result + '" /></p>'); }};
      leitor.readAsDataURL(arquivo);
    }}
  }}; }});
}} }});
CKEDITOR.plugins.add('salvarsei', {{ init: function (editor) {{
  editor.addCommand('salvarsei', {{ exec: function (ed) {{
    fetch('controlador.php?acao=editor_salvar&id_documento={id_doc}', {{ method: 'POST', body: ed.getData() }})
      .then(function (r) {{ return r.text(); }})
      .then(function (t) {{ if (t !== 'OK') {{ document.getElementById('msg').innerText = t; alert(t); }} }});
  }} }});
  editor.ui.addButton('Save', {{ label: 'Salvar', command: 'salvarsei' }});
}} }});
CKEDITOR.replace('txaEditor_{id_doc}', {{
  extraPlugins: 'base64image,salvarsei',
  removePlugins: 'scayt,magicline,uploadimage,uploadwidget,elementspath,image',
  toolbar: [['Save', 'base64image']], versionCheck: false, allowedContent: true, height: 400, language: 'pt-br'
}});
"""
        return _pagina(
            f"SEI - Editor {id_doc}",
            "<div id='divCabecalho'>Cabeçalho fixo</div><div id='msg'></div>"
            f"<textarea id='txaEditor_{id_doc}'>{html.escape(doc['html'])}</textarea>"
            f"<script>{script}</script>",
            head="<script src='/ckeditor/ckeditor.js'></script>",
        )

    def _salvar(self, route, request, q: dict) -> None:
        doc = self.documentos[int(q["id_documento"]) - 1]
        corpo = request.post_data or ""
        if self.falhas_salvar.get(doc["id"], 0) > 0:
            self.falhas_salvar[doc["id"]] -= 1
            return route.fulfill(status=200, content_type="text/plain", body="Falha de comunicação com o servidor.")
        if len(corpo.encode("utf-8")) > self.limite_bytes:
            return route.fulfill(status=200, content_type="text/plain", body=MENSAGEM_TAMANHO)
        doc["html"] = corpo
        doc["salvamentos"] += 1
        route.fulfill(status=200, content_type="text/plain", body="OK")

    # ------------------------------------------------------------ para os testes

    @staticmethod
    def qtd_imagens(doc: dict) -> int:
        return len(re.findall(r"<img\b", doc["html"]))
