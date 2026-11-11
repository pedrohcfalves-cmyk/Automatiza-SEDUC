"""SIGEF simulado para testes: imita as telas 1028 (credor) e 351 (domicílio).

Reproduz os mesmos IDs, pop-ups, postbacks e mensagens usados pela automação.
Uso isolado:  python testes/sigef_simulado.py 8765
"""

import html
import sys
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MANTER = "/SIGEF2026/ADM/ADMManterCredorGeral.aspx"
PESQUISA_CREDOR = "/SIGEF2026/ADM/ADMPesquisarCredor.aspx"
DOMICILIO = "/SIGEF2026/FIN/FINIncluirDomicilioBancarioCredor.aspx"
PESQUISA_DOMICILIO = "/SIGEF2026/FIN/FINPesquisarCredor.aspx"

SUCESSO = "Operação realizada com sucesso."
DOMICILIO_REPETIDO = "Domicílio Bancário Credor já cadastrado(a)."


class Estado:
    def __init__(self):
        self.credores = {}       # cpf -> nome
        self.domicilios = set()  # (cpf, banco, agência, conta)
        self.cpfs_invalidos = {"00000000000"}  # a "Receita" recusa
        self.trava = threading.Lock()


def _pagina(titulo: str, corpo: str) -> bytes:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{titulo}</title></head><body>{corpo}</body></html>"
    ).encode("utf-8")


def _mensagem(classe: str, texto: str) -> str:
    return f"<table><tr><td class='{classe}'>{html.escape(texto)}</td></tr></table>"


def _linha_resultado(cpf: str, nome: str, ao_clicar: str) -> str:
    return (f"<table id='dtgCredor'><tr><th>CPF</th><th>Nome</th></tr>"
            f"<tr><td onclick=\"{ao_clicar}\">{cpf}</td><td>{html.escape(nome)}</td></tr></table>")


def criar_servidor(porta: int = 0, estado: Estado = None):
    estado = estado or Estado()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        # ------------------------------------------------------ infra
        def _logado(self) -> bool:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return "sessao" in cookie

        def _form(self) -> dict:
            tamanho = int(self.headers.get("Content-Length") or 0)
            dados = parse_qs(self.rfile.read(tamanho).decode("utf-8"))
            return {chave: valores[0] for chave, valores in dados.items()}

        def _enviar(self, corpo: bytes, extra_headers=()):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")

            for chave, valor in extra_headers:
                self.send_header(chave, valor)

            self.end_headers()
            self.wfile.write(corpo)

        # ------------------------------------------------------ rotas
        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}

            if url.path in ("/", "/login"):
                return self._enviar(self._tela_login())

            if not self._logado():
                return self._enviar(_pagina("SIGEF", "<p>Sessão expirada. Faça o login.</p>"))

            if url.path == MANTER:
                return self._enviar(self._tela_manter(cpf=query.get("cpf", "")))

            if url.path == DOMICILIO:
                return self._enviar(self._tela_domicilio())

            if url.path in (PESQUISA_CREDOR, PESQUISA_DOMICILIO):
                return self._enviar(self._tela_pesquisa(url.path, query))

            self.send_error(404)

        def do_POST(self):
            url = urlparse(self.path)
            form = self._form()

            if url.path == "/login":
                return self._enviar(
                    _pagina("SIGEF", "<p id='bemvindo'>Bem-vindo ao SIGEF</p>"),
                    [("Set-Cookie", "sessao=1; Path=/")],
                )

            if not self._logado():
                return self._enviar(_pagina("SIGEF", "<p>Sessão expirada.</p>"))

            if url.path == MANTER:
                return self._enviar(self._postback_manter(form))

            if url.path == DOMICILIO:
                return self._enviar(self._postback_domicilio(form))

            self.send_error(404)

        # ------------------------------------------------------ telas
        def _tela_login(self) -> bytes:
            return _pagina("SIGEF - Login", (
                "<form method='post' action='/login'>"
                "<input id='usuario' name='usuario'><input id='senha' type='password'>"
                "<button id='entrar' type='submit'>Entrar</button></form>"
            ))

        def _tela_manter(self, cpf="", nome="", mensagem="") -> bytes:
            return _pagina("Manter Credor", (
                f"<form method='post' action='{MANTER}?CdTransacao=1028'>"
                "<select id='cmbTipoCredor' name='tipo'>"
                "<option value=''>Selecione</option><option value='10'>Pessoa Física</option>"
                "<option value='20'>Pessoa Jurídica</option></select>"
                "<button type='button' id='btnManutencao_BtnListar' "
                f"onclick=\"window.open('{PESQUISA_CREDOR}', '_blank')\">Listar</button>"
                f"<input id='txtCPF' name='cpf' value='{html.escape(cpf)}'>"
                "<button id='btnReceitaFederal' name='acao' value='receita'>Receita</button>"
                f"<input id='txtNmCredor' name='nome' value='{html.escape(nome)}'>"
                "<button id='btnManutencao_BtnIncluir' name='acao' value='incluir'>Incluir</button>"
                f"</form>{mensagem}"
            ))

        def _postback_manter(self, form: dict) -> bytes:
            cpf, nome, acao = form.get("cpf", ""), form.get("nome", ""), form.get("acao")

            if acao == "receita":
                if cpf in estado.cpfs_invalidos:
                    erro = _mensagem("SIGEFMensagemErro", "CPF inválido na Receita Federal.")
                    return self._tela_manter(cpf, "", erro)

                return self._tela_manter(cpf, "NOME DA RECEITA")

            if acao == "incluir":
                if cpf in estado.cpfs_invalidos:
                    erro = _mensagem("SIGEFMensagemErro", "CPF inválido na Receita Federal.")
                    return self._tela_manter(cpf, nome, erro)

                with estado.trava:
                    if cpf in estado.credores:
                        erro = _mensagem("SIGEFMensagemErro", "Credor já cadastrado(a).")
                        return self._tela_manter(cpf, nome, erro)

                    estado.credores[cpf] = nome

                return self._tela_manter(cpf, nome, _mensagem("SIGEFMensagemSucesso", SUCESSO))

            return self._tela_manter(cpf, nome)

        def _tela_pesquisa(self, caminho: str, query: dict) -> bytes:
            dominio = caminho == PESQUISA_DOMICILIO
            campo = "txtNuCpf" if dominio else "txtCPF"
            cpf = query.get(campo, "")
            resultado = ""

            # Como no SIGEF, a pesquisa continua aberta depois do clique (é fechada pela automação)
            if "buscar" in query and cpf in estado.credores:
                if dominio:
                    clique = (f"window.opener.document.getElementById('hdnCredor').value='{cpf}';"
                              "document.body.append('Selecionado');")
                else:
                    clique = (f"window.opener.document.getElementById('txtCPF').value='{cpf}';"
                              "document.body.append('Selecionado');")

                resultado = _linha_resultado(cpf, estado.credores[cpf], clique)

            elif "buscar" in query:
                resultado = "<p>Nenhum registro encontrado.</p>"

            botao_cpf = ("<button type='button' id='btnCPF' "
                         "onclick=\"document.getElementById('txtNuCpf').style.display=''\">"
                         "CPF</button>") if dominio else ""
            oculto = " style='display:none'" if dominio and not cpf else ""

            return _pagina("Pesquisar Credor", (
                f"<form method='get' action='{caminho}'>{botao_cpf}"
                f"<input id='{campo}' name='{campo}' value='{cpf}'{oculto}>"
                "<input type='hidden' name='buscar' value='1'>"
                "<button id='btnConfirmar' type='submit'>Confirmar</button>"
                f"</form>{resultado}"
            ))

        def _tela_domicilio(self, mensagem="") -> bytes:
            return _pagina("Incluir Domicílio Bancário", (
                f"<form method='post' action='{DOMICILIO}?CdTransacao=351'>"
                "<input type='hidden' id='hdnCredor' name='credor'>"
                "<button type='button' id='txtCdCredor_BtnPesquisa' "
                f"onclick=\"window.open('{PESQUISA_DOMICILIO}', '_blank')\">...</button>"
                "<input id='txtBanco_SIGEFPesquisa' name='banco'>"
                "<input id='txtAgBancaria_SIGEFPesquisa' name='agencia'>"
                "<input id='txtContaBancaria' name='conta'>"
                "<input id='txtNmContaBancaria' name='nome'>"
                "<button id='btnConfirmar' type='submit'>Confirmar</button>"
                f"</form>{mensagem}"
            ))

        def _postback_domicilio(self, form: dict) -> bytes:
            cpf = form.get("credor", "")
            chave = (cpf, form.get("banco", ""), form.get("agencia", ""), form.get("conta", ""))

            if cpf not in estado.credores:
                return self._tela_domicilio(_mensagem("SIGEFMensagemErro", "Credor não informado."))

            with estado.trava:
                if chave in estado.domicilios:
                    erro = _mensagem("SIGEFMensagemErro", DOMICILIO_REPETIDO)
                    return self._tela_domicilio(erro)

                estado.domicilios.add(chave)

            return self._tela_domicilio(_mensagem("SIGEFMensagemSucesso", SUCESSO))

    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    servidor.estado = estado
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


if __name__ == "__main__":
    srv = criar_servidor(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print(f"SIGEF simulado em http://127.0.0.1:{srv.server_address[1]}  (Ctrl+C encerra)")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
