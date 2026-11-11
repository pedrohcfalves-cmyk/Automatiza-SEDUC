"""
SIGEF SIMULADO para os testes -- só as telas e os ids que a Etapa Anexar
Documento (etapa_listar_baixar.py) usa, servidos pelo próprio Playwright
(context.route), sem rede e sem tocar no SIGEF de verdade.

Telas simuladas (mesmos ids do SIGEF real):

    Listar Preparação de Pagamento   #txtGestao_SIGEFPesquisa #txtPrepPagSeq #btnConfirmar  grade #dtgPP
    Detalhar PP                      #txtNuDespesaCertificada #txtNotaLancamento #txtNuOrdemBancaria
    Detalhar Despesa Certificada     a[title="Gerar Relatório"]
    Listar Ordem Bancária            #txtCdGestao_SIGEFPesquisa #txtOBNumero #cboSituacaoOB  grade #dtgListarOrdemBancaria
    Detalhar Ordem Bancária          grade #grdPreparacaoPagamento (a.GridLink + tabelinha de fonte)
    Listar NL                        #txtUnidadeGestora #txtNuNotaLancamentoAno #txtNuNotaLancamento  grade #dtgNotaLancamento
    Imprimir OB Conferência          #txtOrdemBancariaAInicio_SIGEFPesquisa #txtOrdemBancariaAFim_SIGEFPesquisa
    Selecione o tipo de arquivo      img[alt="Imprime Arquivo Formato PostScript (.pdf)"] -> download do PDF

Cada janela de detalhe abre com window.open (popup), como no SIGEF.
"""
import html
import json
import re
from urllib.parse import parse_qs, quote, urlparse

import pymupdf

DOMINIO = "sigef.sefin.ro.gov.br"


def _seq(numero: str) -> int | None:
    """'2026PP039778' / '039778' -> 39778."""
    grupos = re.findall(r"\d+", re.sub(r"^\d{4}[A-Za-z]{2}", "", str(numero or "")))
    return int(max(grupos, key=len)) if grupos else None


def _pdf(titulo: str, paginas: int) -> bytes:
    doc = pymupdf.open()
    for i in range(1, paginas + 1):
        pagina = doc.new_page()
        pagina.insert_text((72, 100), f"{titulo} - pagina {i}/{paginas}", fontsize=18)
    dados = doc.tobytes()
    doc.close()
    return dados


def _pagina(titulo: str, corpo: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(titulo)}</title></head><body><h3>{html.escape(titulo)}</h3>{corpo}</body></html>"
    )


class SigefSimulado:
    """
    Estado do SIGEF falso.

        pps    {"2026PP039778": {"ce": "...", "nl": "...", "ob": "...", "valor": "39,00"}}
        obs    {"2026OB136475": {"situacao": "10", "pps": ["2026PP039778"], "listavel": True}}
        nls    {"2026NL066235", ...}  -- as que aparecem em "Listar NL"
    """

    def __init__(self, pps: dict, obs: dict, nls=None, paginas_ob: int = 2, desviar_pp_apos_ce: bool = False,
                 ce_na_tela=None):
        self.pps = pps
        self.obs = obs
        self.nls = set(nls if nls is not None else {d["nl"] for d in pps.values() if d.get("nl")})
        self.paginas_ob = paginas_ob
        self.desviar_pp_apos_ce = desviar_pp_apos_ce
        # Como a tela da PP escreve a CE: função (ce) -> texto. Padrão: '2026CE018705'.
        self.ce_na_tela = ce_na_tela or (lambda ce: f"2026CE{ce}" if ce and ce.isdigit() else (ce or ""))
        self.requisicoes: list[str] = []
        self.downloads: list[tuple[str, str]] = []
        # Despesas Certificadas incluídas na tela "Manter Despesa Certificada".
        self.ces_registradas: list[dict] = []
        self.proxima_ce = 18705
        # Preparações de Pagamento confirmadas na tela da PP.
        self.pps_registradas: list[dict] = []
        self.proxima_pp = 39778
        # True: banco/agência/conta somem quando o serviço não é Crédito
        # conta-corrente (para testar os dois comportamentos).
        self.pp_esconde_conta_sem_credito = False
        # OBs incluídas na tela "Manter Ordem Bancária" e as PPs (com valor)
        # que a busca de PP da OB mostra: [("2026PP039778", "39,00"), ...].
        self.obs_registradas: list[dict] = []
        self.proxima_ob = 136475
        self.pps_para_ob: list[tuple[str, str]] = []
        self.buscas_pp_ob: list[dict] = []
        # Tela "Liquidar Despesa Certificada" (NL): NLs que já existem na CE
        # (aparecem na grade ao pesquisar) [("2026NL066000", "857,50")],
        # NLs incluídas, lotes finalizados e valores que "falham" (não geram NL).
        self.nls_existentes: list[tuple[str, str]] = []
        self.nls_registradas: list[dict] = []
        self.proxima_nl = 66235
        self.nl_lotes_finalizados = 0
        self.nl_valores_que_falham: set[str] = set()

    # ------------------------------------------------------------ roteamento

    def instalar(self, context) -> None:
        context.route(re.compile(rf"https?://{re.escape(DOMINIO)}/.*"), self._atender)

    def _responder(self, route, corpo: str) -> None:
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)

    def _atender(self, route, request) -> None:
        url = urlparse(request.url)
        nome = url.path.rsplit("/", 1)[-1]
        q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        self.requisicoes.append(nome)

        if nome == "FINListarPreparacaoPagamento.aspx":
            return self._responder(route, self._listar_pp(q))
        if nome == "FINDetalharPreparacaoPagamentoDespesaEmpenhada.aspx":
            return self._responder(route, self._detalhe_pp(q))
        if nome == "FINDetalharDespesaCertificada.aspx":
            return self._responder(route, self._detalhe_ce(q))
        if nome == "FINListarOrdemBancaria.aspx":
            return self._responder(route, self._listar_ob(q))
        if nome == "FINDetalharOrdemBancaria.aspx":
            return self._responder(route, self._detalhe_ob(q))
        if nome == "FINListarNotaLancamentoLiquidacao.aspx":
            return self._responder(route, self._listar_nl(q))
        if nome == "FINDetalharNotaLancamento.aspx":
            return self._responder(route, self._detalhe_nl(q))
        if nome == "FINImprimirOrdemBancariaConferencia.aspx":
            return self._responder(route, self._conferencia_ob())
        if nome == "FINManterDespesaCertificada.aspx":
            return self._responder(route, self._manter_ce())
        if nome == "FINPesquisarCredor.aspx":
            return self._responder(route, self._pesquisar_credor())
        if nome == "RegistrarCE.aspx":
            dados = json.loads(request.post_data or "{}")
            self.ces_registradas.append(dados)
            numero = f"{self.proxima_ce:06d}"
            self.proxima_ce += 1
            return route.fulfill(status=200, content_type="text/plain", body=numero)
        if nome == "FINPreparacaoPagamentoDespesaEmpenhada.aspx":
            return self._responder(route, self._tela_pp())
        if nome == "FINPesquisarNotaLancamento.aspx":
            return self._responder(route, _pagina(
                "Pesquisar Nota de Lançamento",
                "<a href='#' id='lnkNaoObedeceOrdemCronologica' "
                "onclick=\"window.open('FINGerarOrdemCronologica.aspx','_blank');return false;\">"
                "Não obedece ordem cronológica</a>",
            ))
        if nome == "FINGerarOrdemCronologica.aspx":
            return self._responder(route, self._gerar_ordem_cronologica())
        if nome == "RegistrarPP.aspx":
            dados = json.loads(request.post_data or "{}")
            self.pps_registradas.append(dados)
            numero = f"2026PP{self.proxima_pp:06d}"
            self.proxima_pp += 1
            return route.fulfill(status=200, content_type="text/plain", body=numero)
        if nome == "FINLiquidarDespesaCertificada.aspx":
            return self._responder(route, self._tela_nl())
        if nome == "FINPesquisarNotaEmpenho.aspx":
            return self._responder(route, self._pesquisar_ne())
        if nome == "RegistrarNL.aspx":
            dados = json.loads(request.post_data or "{}")
            if dados.get("valor") in self.nl_valores_que_falham:
                return route.fulfill(status=200, content_type="text/plain", body="")
            self.nls_registradas.append(dados)
            numero = f"2026NL{self.proxima_nl:06d}"
            self.proxima_nl += 1
            return route.fulfill(status=200, content_type="text/plain", body=numero)
        if nome == "FinalizarNL.aspx":
            self.nl_lotes_finalizados += 1
            return route.fulfill(status=200, content_type="text/plain", body="OK")
        if nome == "FINManterOrdemBancaria.aspx":
            return self._responder(route, self._tela_ob())
        if nome == "FINAdicionarPPOrdemBancaria.aspx":
            return self._responder(route, self._busca_pp_ob(q))
        if nome == "RegistrarOB.aspx":
            dados = json.loads(request.post_data or "{}")
            self.obs_registradas.append(dados)
            numero = f"2026OB{self.proxima_ob:06d}"
            self.proxima_ob += 1
            return route.fulfill(status=200, content_type="text/plain", body=numero)
        if nome == "Formato.aspx":
            return self._responder(route, self._formato(q))
        if nome == "Download.aspx":
            doc, num = q.get("doc", ""), q.get("num", "")
            self.downloads.append((doc, num))
            paginas = self.paginas_ob if doc == "OB" else 1
            return route.fulfill(
                status=200,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'attachment; filename="{doc}_{_seq(num)}.pdf"',
                },
                body=_pdf(f"{doc} {num}", paginas),
            )
        return self._responder(route, _pagina("SIGEF", "<p>tela inicial</p>"))

    # ------------------------------------------------------------ telas

    @staticmethod
    def _abrir(url: str) -> str:
        return f"window.open('{url}','_blank');return false;"

    def _botao_imprimir(self, doc: str, num: str, extra_js: str = "") -> str:
        destino = f"Formato.aspx?doc={doc}&num={quote(num)}"
        return (
            f"<a id='btnBotoesImpressao_btnImprimir' title='Gerar Relatório' href='#' "
            f"onclick=\"{extra_js}window.open('{destino}','_blank');return false;\">"
            "<img id='btnBotoesImpressao_BtnImprimir' alt='Imprimir'></a>"
        )

    def _listar_pp(self, q: dict) -> str:
        form = (
            "<form method='get' action='FINListarPreparacaoPagamento.aspx'>"
            "<input type='hidden' name='CdTransacao' value='177'>"
            f"<input id='txtGestao_SIGEFPesquisa' name='gestao' value='{html.escape(q.get('gestao', ''))}'>"
            f"<input id='txtPrepPagSeq' name='seq' value='{html.escape(q.get('seq', ''))}'>"
            "<input type='submit' id='btnConfirmar' value='Confirmar'></form>"
        )
        grade = ""
        if q.get("seq"):
            linhas = []
            for i, (pp, dados) in enumerate(self.pps.items()):
                if _seq(pp) == _seq(q["seq"]) and dados.get("listavel_pp", True):
                    detalhe = (
                        "FINDetalharPreparacaoPagamentoDespesaEmpenhada.aspx?CdUnidadeGestora=160001"
                        f"&CdGestao=1&NuPreparacaoPagamento={pp}"
                    )
                    classe = "GridLinhaPar" if i % 2 == 0 else "GridLinhaImpar"
                    linhas.append(
                        f"<tr class='{classe}'><td class='GridLink' onclick=\"{self._abrir(detalhe)}\">{pp}</td>"
                        f"<td>{dados.get('valor', '')}</td></tr>"
                    )
            grade = "<table id='dtgPP'><tr class='GridCabecalho'><td>PP</td><td>Valor</td></tr>" + "".join(linhas) + "</table>" if linhas else ""
        return _pagina("Listar Preparação de Pagamento", form + grade)

    def _detalhe_pp(self, q: dict) -> str:
        pp = q.get("NuPreparacaoPagamento", "")
        dados = self.pps.get(pp)
        if dados is None:
            return _pagina("Erro", "<p>PP não encontrada</p>")
        ce_tela = self.ce_na_tela(dados.get("ce"))
        ce = (
            f"<input id='txtNuDespesaCertificada' readonly value='{ce_tela}' "
            f"onclick=\"if(this.value){{window.open('FINDetalharDespesaCertificada.aspx?ce={quote(ce_tela)}&pp={pp}','_blank');}}\">"
        )
        nl = f"<input id='txtNotaLancamento' readonly value='{dados.get('nl_tela', dados.get('nl', ''))}'>"
        ob = f"<input id='txtNuOrdemBancaria' readonly value='{dados.get('ob_tela', dados.get('ob', ''))}'>"
        return _pagina(
            "Detalhar Preparação Pagamento Despesa Empenhada",
            f"<p>PP {pp}</p>{ce}{nl}{ob}" + self._botao_imprimir("PP", pp),
        )

    def _detalhe_ce(self, q: dict) -> str:
        ce, pp = q.get("ce", ""), q.get("pp", "")
        extra = ""
        if self.desviar_pp_apos_ce:
            ob = self.pps.get(pp, {}).get("ob", "")
            extra = (
                "try{window.opener.location.href='FINDetalharOrdemBancaria.aspx?CdUnidadeGestora=160001"
                f"&CdGestao=00001&NuOrdemBancaria={ob}';}}catch(e){{}};"
            )
        return _pagina("Detalhar Despesa Certificada", f"<p>CE {ce}</p>" + self._botao_imprimir("CE", ce, extra))

    def _listar_ob(self, q: dict) -> str:
        situacao = q.get("situacao", "")
        opcoes = "".join(
            f"<option value='{v}'{' selected' if v == situacao else ''}>{t}</option>"
            for v, t in (("", "Todas"), ("5", "Emitida"), ("10", "Paga"))
        )
        form = (
            "<form method='get' action='FINListarOrdemBancaria.aspx'>"
            "<input type='hidden' name='CdTransacao' value='175'>"
            f"<input id='txtCdGestao_SIGEFPesquisa' name='gestao' value='{html.escape(q.get('gestao', ''))}'>"
            f"<input id='txtOBNumero' name='ob' value='{html.escape(q.get('ob', ''))}'>"
            f"<select id='cboSituacaoOB' name='situacao'>{opcoes}</select>"
            "<input type='submit' id='btnConfirmar' value='Confirmar'></form>"
        )
        grade = ""
        if "ob" in q:
            linhas = []
            for ob, dados in self.obs.items():
                if not dados.get("listavel", True):
                    continue
                if _seq(ob) != _seq(q["ob"]):
                    continue
                if situacao and dados.get("situacao", "10") != situacao:
                    continue
                detalhe = f"FINDetalharOrdemBancaria.aspx?CdUnidadeGestora=160001&CdGestao=00001&NuOrdemBancaria={ob}"
                linhas.append(
                    f"<tr class='GridLinhaPar'><td class='GridLink' onclick=\"{self._abrir(detalhe)}\">{ob}</td></tr>"
                )
            # Grade vazia também aparece (como no SIGEF), só sem linhas.
            grade = "<table id='dtgListarOrdemBancaria'><tr class='GridCabecalho'><td>OB</td></tr>" + "".join(linhas) + "</table>"
        return _pagina("Listar Ordem Bancária", form + grade)

    def _detalhe_ob(self, q: dict) -> str:
        ob = q.get("NuOrdemBancaria", "")
        dados = self.obs.get(ob)
        if dados is None:
            return _pagina("Erro", "<p>OB não encontrada</p>")
        linhas = []
        for pp in dados["pps"]:
            valor = self.pps.get(pp, {}).get("valor_na_ob", self.pps.get(pp, {}).get("valor", "0,00"))
            detalhe = (
                "FINDetalharPreparacaoPagamentoDespesaEmpenhada.aspx?CdUnidadeGestora=160001"
                f"&CdGestao=1&NuPreparacaoPagamento={pp}"
            )
            linhas.append(
                "<tr class='GridLinhaPar'>"
                f"<td><a class='GridLink' href='#' onclick=\"{self._abrir(detalhe)}\">{pp}</a></td>"
                "<td>03.508.155/0001-21</td>"
                "<td><table><tr class='GridLinhaPar'><td>500001001</td></tr></table></td>"
                f"<td>{valor}</td></tr>"
            )
        grade = "<table id='grdPreparacaoPagamento'>" + "".join(linhas) + "</table>"
        return _pagina("Detalhar Ordem Bancária", f"<p>OB {ob}</p>" + grade)

    def _listar_nl(self, q: dict) -> str:
        form = (
            "<form method='get' action='FINListarNotaLancamentoLiquidacao.aspx'>"
            f"<input id='txtUnidadeGestora' name='ug' value='{html.escape(q.get('ug', '160001'))}'>"
            f"<input id='txtGestao_SIGEFPesquisa' name='gestao' value='{html.escape(q.get('gestao', '00001'))}'>"
            f"<input id='txtNuNotaLancamentoAno' name='ano' value='{html.escape(q.get('ano', ''))}'>"
            f"<input id='txtNuNotaLancamento' name='seq' value='{html.escape(q.get('seq', ''))}'>"
            "<input type='submit' id='btnPesquisar' value='Pesquisar'></form>"
        )
        grade = ""
        if q.get("seq"):
            linhas = []
            for nl in sorted(self.nls):
                if nl.startswith(q.get("ano", "")) and _seq(nl) == _seq(q["seq"]):
                    detalhe = f"FINDetalharNotaLancamento.aspx?nl={nl}"
                    linhas.append(
                        f"<tr class='GridLinhaPar'><td class='GridLink' onclick=\"{self._abrir(detalhe)}\">{nl}</td></tr>"
                    )
            grade = "<table id='dtgNotaLancamento'>" + "".join(linhas) + "</table>"
        return _pagina("Listar Nota Lançamento Liquidação", form + grade)

    def _detalhe_nl(self, q: dict) -> str:
        nl = q.get("nl", "")
        return _pagina("Detalhar Nota Lançamento Liquidação", f"<p>NL {nl}</p>" + self._botao_imprimir("NL", nl))

    def _conferencia_ob(self) -> str:
        existentes = ",".join(str(_seq(ob)) for ob in self.obs)
        completas = "{" + ",".join(f"'{_seq(ob)}':'{ob}'" for ob in self.obs) + "}"
        js = (
            "var ini=document.getElementById('txtOrdemBancariaAInicio_SIGEFPesquisa').value;"
            "var fim=document.getElementById('txtOrdemBancariaAFim_SIGEFPesquisa').value;"
            f"var mapa={completas};var n=String(parseInt(ini,10));"
            "if(!/^\\d+$/.test(ini)||fim!==ini||!(n in mapa)){document.getElementById('critica').innerText='OB inexistente';return false;}"
            "window.open('Formato.aspx?doc=OB&num='+mapa[n],'_blank');return false;"
        )
        return _pagina(
            "Imprimir Ordem Bancária Conferência",
            "<input id='txtCdGestao_SIGEFPesquisa'>"
            "<input id='txtOrdemBancariaAInicio_SIGEFPesquisa'>"
            "<input id='txtOrdemBancariaAFim_SIGEFPesquisa'>"
            f"<span id='critica' data-obs='{existentes}'></span>"
            f"<a title='Gerar Relatório' href='#' onclick=\"{js}\"><img alt='Imprimir'></a>",
        )

    def _manter_ce(self) -> str:
        opcoes_tipo = "".join(
            f"<option value='{v}'{' selected' if v == '6' else ''}>{v}</option>"
            for v in ("6", "8", "11", "9", "13", "14", "16", "5", "7", "15", "1", "2", "12", "4", "3", "99", "10")
        )
        opcoes_mes = "<option value=''></option>" + "".join(f"<option value='{m}'>{m}</option>" for m in range(1, 14))
        js = """
var NF=['1','2','3','4','12'];
function v(id){var e=document.getElementById(id);return e?e.value:'';}
function trocarTipo(){document.getElementById('divNF').style.display=NF.indexOf(v('cmbCdTipoDocumento'))>=0?'block':'none';}
function incluir(){
  var d={ug:v('txtCdUnidadeGestora'),gestao:v('txtCdGestao_SIGEFPesquisa'),tipo:v('cmbCdTipoDocumento'),
    subserie:v('txtNuSubSerie'),serie:v('txtNuSerie'),modelo:v('txtNmModelo'),numdoc:v('txtNuDocumento'),
    atestado:document.getElementById('chkFlAtestadoRecSouResp').checked,
    dt_aceite:v('txtDtAceite_SIGEFData'),dt_apresentacao:v('txtDtApresentacao_SIGEFData'),dt_emissao:v('txtDtEmissao_SIGEFData'),
    mes:v('cboMesComp'),obs:v('txtDeObservacao'),credor:v('hdnCredor'),valor:v('txtVlDocumento')};
  var erro=document.getElementById('erro');
  if(NF.indexOf(d.tipo)>=0&&(!d.subserie||!d.serie||!d.modelo)){erro.innerText='Informe Subsérie, Série e Modelo.';return false;}
  if(!d.mes||!d.credor||!d.valor){erro.innerText='Campos obrigatórios.';return false;}
  fetch('RegistrarCE.aspx',{method:'POST',body:JSON.stringify(d)}).then(function(r){return r.text();})
    .then(function(n){setTimeout(function(){document.getElementById('txtNuSeq').value=n;},400);});
  return false;
}"""
        return _pagina(
            "Manter Despesa Certificada",
            "<input id='txtNuSeq'>"
            "<input id='txtCdUnidadeGestora'><input id='txtCdGestao_SIGEFPesquisa'>"
            f"<select id='cmbCdTipoDocumento' onchange='trocarTipo()'>{opcoes_tipo}</select>"
            "<div id='divNF' style='display:none'><input id='txtNuSubSerie' maxlength='7'>"
            "<input id='txtNuSerie' maxlength='7'><input id='txtNmModelo' maxlength='20'></div>"
            "<input id='txtNuDocumento'><input type='checkbox' id='chkFlAtestadoRecSouResp'>"
            "<input id='txtDtAceite_SIGEFData'><input id='txtDtApresentacao_SIGEFData'><input id='txtDtEmissao_SIGEFData'>"
            f"<select id='cboMesComp'>{opcoes_mes}</select><textarea id='txtDeObservacao'></textarea>"
            "<input id='txtNmCredor' readonly><input type='hidden' id='hdnCredor'>"
            "<a href='#' id='txtNmCredor_BtnPesquisa' onclick=\"window.open('FINPesquisarCredor.aspx','_blank');return false;\">buscar</a>"
            "<input id='txtVlDocumento'>"
            "<a href='#' id='btnManutencao_BtnIncluir' onclick='return incluir()'>Incluir</a>"
            f"<div id='erro'></div><script>{js}</script>",
        )

    def _pesquisar_credor(self) -> str:
        js = """
function modoCPF(){document.getElementById('divCnpj').style.display='none';document.getElementById('divCpf').style.display='block';return false;}
function confirmar(){
  var cpf=document.getElementById('divCpf').style.display==='block';
  var n=cpf?document.getElementById('txtNuCpf').value:document.getElementById('txtNuCnpj').value;
  if(!n){return false;}
  var chave=(cpf?'cpf:':'cnpj:')+n;
  var td=document.createElement('td');td.className='GridLink';td.textContent='CREDOR '+n;td.setAttribute('onclick','SelecionarItem(this.dataset.chave)');td.dataset.chave=chave;var tr=document.createElement('tr');tr.className='GridLinhaPar';tr.appendChild(td);var t=document.createElement('table');t.appendChild(tr);document.getElementById('grade').appendChild(t);
  return false;
}
function SelecionarItem(chave){window.opener.document.getElementById('hdnCredor').value=chave;
  window.opener.document.getElementById('txtNmCredor').value=chave;}"""
        return _pagina(
            "Pesquisar Credor",
            "<div id='divCnpj'><input id='txtNuCnpj'></div>"
            "<div id='divCpf' style='display:none'><input id='txtNuCpf' maxlength='14'></div>"
            "<input type='image' id='btnCPF' alt='CPF' style='width:40px;height:20px' onclick='return modoCPF()'>"
            "<a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a>"
            f"<div id='grade'></div><script>{js}</script>",
        )

    def _tela_pp(self) -> str:
        esconde = "true" if self.pp_esconde_conta_sem_credito else "false"
        js = """
var ESCONDE=%s;
function v(id){return document.getElementById(id).value;}
function trocarTipoOB(){ /* postback: limpa banco/agência/conta */
  ['txtBanco','txtAgencia','txtConta_SIGEFPesquisa'].forEach(function(id){document.getElementById(id).value='';});}
function trocarServico(){
  document.getElementById('divConta').style.display=(ESCONDE&&v('cboTipoServico')!=='10')?'none':'block';}
function retencoes(){document.getElementById('abas').style.display='block';return false;}
function confirmar(){
  var conta=document.getElementById('divConta').style.display!=='none';
  var d={ug:v('txtUnidadeGestora'),gestao:v('txtGestao_SIGEFPesquisa'),nl:v('hdnNL'),ce:v('hdnCE'),
    tipo_ob:v('cboTipoOrdemBancaria'),servico:v('cboTipoServico'),
    banco:conta?v('txtBanco'):null,agencia:conta?v('txtAgencia'):null,conta:conta?v('txtConta_SIGEFPesquisa'):null};
  var erro=document.getElementById('erro');
  if(!d.nl||!d.tipo_ob){erro.innerText='Campos obrigatórios.';return false;}
  if(d.servico==='10'&&(!d.banco||!d.agencia||!d.conta)){erro.innerText='Informe banco, agência e conta.';return false;}
  fetch('RegistrarPP.aspx',{method:'POST',body:JSON.stringify(d)}).then(function(r){return r.text();})
    .then(function(n){setTimeout(function(){
      document.getElementById('msg').innerHTML="<table><tr><td class='SIGEFMensagemSucesso'>Preparação de Pagamento "+n+" incluída com sucesso.</td></tr></table>";},400);});
  return false;
}
function limpar(){document.getElementById('msg').innerHTML='';document.getElementById('hdnNL').value='';
  document.getElementById('abas').style.display='none';return false;}
""" % esconde
        opcoes_ob = "".join(f"<option value='{v}'>{v}</option>" for v in ("", "1", "2", "3"))
        opcoes_servico = "".join(f"<option value='{v}'>{v}</option>" for v in ("10", "1", "5", "6"))
        return _pagina(
            "Preparação de Pagamento",
            "<input id='txtUnidadeGestora'><input id='txtGestao_SIGEFPesquisa'>"
            "<input type='hidden' id='hdnNL'><input type='hidden' id='hdnCE'>"
            "<a href='#' id='txtNotaLancamento_BtnPesquisa' "
            "onclick=\"window.open('FINPesquisarNotaLancamento.aspx','_blank');return false;\">NL</a>"
            f"<select id='cboTipoOrdemBancaria' onchange='trocarTipoOB()'>{opcoes_ob}</select>"
            f"<select id='cboTipoServico' onchange='trocarServico()'>{opcoes_servico}</select>"
            # Começa com lixo no banco: digitar sem limpar somaria ("999001").
            "<div id='divConta'><input id='txtBanco' value='999'><input id='txtAgencia'>"
            "<input id='txtConta_SIGEFPesquisa'></div>"
            "<a href='#' id='btnRetencoes' onclick='return retencoes()'>Retenções</a>"
            "<div id='abas' style='display:none'><img src='/SIGEF/Imagens/aba_confirmacao.gif' "
            "style='width:40px;height:20px' alt='confirmação'></div>"
            "<a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a>"
            "<img src='/SIGEF/Recursos/Controles/Imagens/Limpar.GIF' style='width:20px;height:20px' "
            "alt='limpar' onclick='limpar()'>"
            f"<div id='erro'></div><div id='msg'></div><script>{js}</script>",
        )

    def _gerar_ordem_cronologica(self) -> str:
        js = """
function confirmar(){
  var nl=document.getElementById('txtNotaLancamento_SIGEFPesquisa').value;
  var ce=document.getElementById('txtDespesaCertificada_SIGEFPesquisa').value;
  var td=document.createElement('td');td.className='GridLink';td.textContent='NL '+nl+' / CE '+ce;
  td.onclick=function(){var p=window.opener.opener.document;p.getElementById('hdnNL').value=nl;
    p.getElementById('hdnCE').value=ce;};
  var tr=document.createElement('tr');tr.appendChild(td);var t=document.createElement('table');t.appendChild(tr);
  document.getElementById('divdtgGerarOrdemCronologica').appendChild(t);return false;}"""
        return _pagina(
            "Gerar Ordem Cronológica",
            "<input id='txtNotaLancamentoSigla'><input id='txtDespesaCertificadaSigla'>"
            "<input id='txtNotaLancamento_SIGEFPesquisa'><input id='txtDespesaCertificada_SIGEFPesquisa'>"
            "<a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a>"
            f"<div id='divdtgGerarOrdemCronologica'></div><script>{js}</script>",
        )

    def _tela_ob(self) -> str:
        js = """
function v(id){return document.getElementById(id).value;}
function adicionar(){window.open('FINAdicionarPPOrdemBancaria.aspx','_blank');return false;}
function incluir(){
  var d={data:document.getElementsByName('txtDataReferencia$SIGEFData')[0].value,ug:v('txtUnidadeGestora'),
    gestao:v('txtGestao_SIGEFPesquisa'),banco:document.getElementsByName('txtBancoOrigem')[0].value,
    agencia:document.getElementsByName('txtAgenciaOrigem')[0].value,conta:document.getElementsByName('txtContaOrigem')[0].value,
    tipo_ob:v('cboTipoOB'),tipo_pagamento:v('cboTipoPagamento'),obs:v('txtDeObservacao'),pp:v('hdnPP')};
  if(!d.pp){document.getElementById('erro').innerText='Adicione a PP.';return false;}
  fetch('RegistrarOB.aspx',{method:'POST',body:JSON.stringify(d)}).then(function(r){return r.text();})
    .then(function(n){setTimeout(function(){document.getElementById('msg').innerHTML=
      "<table><tr><td class='SIGEFMensagemSucesso'>Ordem Bancária "+n+" incluída com sucesso.</td></tr></table>";
      document.getElementById('itens').innerHTML="<input type='checkbox' id='chk0'>";},400);});
  return false;}"""
        opcoes_ob = "".join(f"<option value='{v}'{' selected' if v == '2' else ''}>{v}</option>" for v in ("", "1", "2", "3", "4"))
        opcoes_pag = "".join(f"<option value='{v}'{' selected' if v == '2' else ''}>{v}</option>" for v in ("1", "2", "3", "4"))
        return _pagina(
            "Manter Ordem Bancária",
            "<input name='txtDataReferencia$SIGEFData'><input id='txtUnidadeGestora'><input id='txtGestao_SIGEFPesquisa'>"
            # Começa com lixo no banco: digitar sem limpar somaria ("999001").
            "<input name='txtBancoOrigem' value='999'><input name='txtAgenciaOrigem'><input name='txtContaOrigem'>"
            f"<select id='cboTipoOB'>{opcoes_ob}</select><select id='cboTipoPagamento'>{opcoes_pag}</select>"
            "<textarea id='txtDeObservacao'></textarea><input type='hidden' id='hdnPP'>"
            "<a href='#' id='btnAdicionar' onclick='return adicionar()'>Adicionar</a>"
            "<a href='#' id='SIGEFBotoesManutencao_BtnIncluir' onclick='return incluir()'>Incluir</a>"
            "<input id='txtNumeroOB'><div id='itens'></div><a href='#' id='btnRemover'>Remover</a>"
            f"<div id='erro'></div><div id='msg'></div><script>{js}</script>",
        )

    def _busca_pp_ob(self, q: dict) -> str:
        if "fonte" in q:
            self.buscas_pp_ob.append(dict(q))
        linhas = ""
        if "fonte" in q:
            for i, (pp, valor) in enumerate(self.pps_para_ob):
                tds = [f"<td>c{n}</td>" for n in range(16)]
                tds[0] = f"<td><input type='checkbox' id='chk{i}' data-pp='{pp}'></td>"
                tds[6] = f"<td>{pp}</td>"
                tds[15] = f"<td>{valor}</td>"
                linhas += f"<tr class='{'GridLinhaPar' if i % 2 == 0 else 'GridLinhaImpar'}'>{''.join(tds)}</tr>"
        js = """
function confirmar(){var marcados=document.querySelectorAll('input[type=checkbox]:checked');
  var pps=[];for(var i=0;i<marcados.length;i++){pps.push(marcados[i].dataset.pp);}
  if(pps.length){window.opener.document.getElementById('hdnPP').value=pps.join(',');}
  setTimeout(function(){window.close();},300);return false;}  /* fecha depois do "postback" */"""
        return _pagina(
            "Adicionar PP",
            "<form method='get' action='FINAdicionarPPOrdemBancaria.aspx'>"
            "<input id='txtUnidadeGestora' name='ug'><input id='txtGestao_SIGEFPesquisa' name='gestao'>"
            "<input id='txtIdUso' name='iduso'><input id='txtFonte_SIGEFPesquisa' name='fonte'>"
            "<input type='submit' id='btnPesquisar' value='Pesquisar'></form>"
            f"<table>{linhas}</table>"
            f"<a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a><script>{js}</script>",
        )

    def _tela_nl(self) -> str:
        existentes = json.dumps(self.nls_existentes)
        js = """
var EXISTENTES=%s;
function v(id){return document.getElementById(id).value;}
function fmt(d){d=String(parseInt(d,10)).padStart(3,'0');var r=d.slice(0,-2),c=d.slice(-2);
  return r.replace(/\\B(?=(\\d{3})+(?!\\d))/g,'.')+','+c;}
function linha(nl,valor){ /* 8 <td> diretos; o 2º tem tabela aninhada com GridLinhaPar */
  var tr=document.createElement('tr');tr.className=(document.querySelectorAll('#dtgDocumentos > tbody > tr, #dtgDocumentos > tr').length%%2)?'GridLinhaImpar':'GridLinhaPar';
  var cel=['x',"<table><tr class='GridLinhaPar'><td>160001</td><td>a</td><td>b</td><td>c</td><td>d</td><td>NL aninhada 999</td></tr></table>",'x','x','x',nl,'x',valor];
  cel.forEach(function(h){var td=document.createElement('td');td.innerHTML=h;tr.appendChild(td);});
  document.getElementById('dtgDocumentos').appendChild(tr);}
function pesquisar(){EXISTENTES.forEach(function(r){linha(r[0],r[1]);});return false;}
function adicionar(){document.getElementById('item').dataset.aberto='1';return false;}
function confirmar(){
  var item=document.getElementById('item');
  if(item.dataset.aberto==='1'){
    var d={ce:v('txtDespesaCertificadaNumero_SIGEFPesquisa'),ne:v('hdnNE'),valor:v('txtValorBrutoId'),venc:v('txtDataVencimento_SIGEFData'),
      retencao:document.getElementById('menun4').dataset.clicado==='1'};
    item.dataset.aberto='0';
    fetch('RegistrarNL.aspx',{method:'POST',body:JSON.stringify(d)}).then(function(r){return r.text();})
      .then(function(n){setTimeout(function(){if(n){linha(n,fmt(d.valor));}
        document.getElementById('hdnNE').value='';document.getElementById('txtValorBrutoId').value='';},500);});
  } else {
    fetch('FinalizarNL.aspx',{method:'POST',body:'{}'});
  }
  return false;}
""" % existentes
        return _pagina(
            "Liquidar Despesa Certificada",
            "<input id='txtCdUnidadeGestora'><input id='txtCdGestao_SIGEFPesquisa'>"
            "<input id='txtDespesaCertificadaNumero_SIGEFPesquisa'>"
            "<a href='#' id='btnPesquisar' onclick='return pesquisar()'>Pesquisar</a>"
            "<div id='item' data-aberto='0'><input id='txtDataVencimento_SIGEFData'>"
            "<a href='#' id='btnAdicionar' onclick='return adicionar()'>Adicionar</a>"
            "<a href='#' id='txtNotaEmpenhoNumeroId_BtnPesquisa' "
            "onclick=\"window.open('FINPesquisarNotaEmpenho.aspx','_blank');return false;\">NE</a>"
            "<input type='hidden' id='hdnNE'><input id='txtValorBrutoId'>"
            "<a href='#' id='btnRetencoesId' onclick='return false;'>Retenções</a>"
            "<a href='#' id='menun4' onclick=\"this.dataset.clicado='1';return false;\">Confirmação</a></div>"
            "<a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a>"
            "<img src='/SIGEF/Recursos/Controles/Imagens/Limpar.GIF' style='width:20px;height:20px' alt='limpar'>"
            f"<table id='dtgDocumentos'></table><script>{js}</script>",
        )

    def _pesquisar_ne(self) -> str:
        js = """
function confirmar(){var ne=document.getElementById('txtNotaEmpenhoNumero').value;
  var td=document.createElement('td');td.className='GridLink';td.textContent='NE '+ne;
  td.setAttribute('onclick','SelecionarItem(this.textContent)');
  var tr=document.createElement('tr');tr.appendChild(td);var t=document.createElement('table');t.appendChild(tr);
  document.getElementById('grade').appendChild(t);return false;}
function SelecionarItem(texto){window.opener.document.getElementById('hdnNE').value=texto.replace('NE ','');}"""
        return _pagina(
            "Pesquisar Nota de Empenho",
            "<input id='txtNotaEmpenhoNumero'><a href='#' id='btnConfirmar' onclick='return confirmar()'>Confirmar</a>"
            f"<div id='grade'></div><script>{js}</script>",
        )

    def _formato(self, q: dict) -> str:
        destino = f"Download.aspx?doc={q.get('doc', '')}&num={quote(q.get('num', ''))}"
        return _pagina(
            "Selecione o tipo de arquivo",
            f"<a href='{destino}'><img alt='Imprime Arquivo Formato PostScript (.pdf)'></a>",
        )
