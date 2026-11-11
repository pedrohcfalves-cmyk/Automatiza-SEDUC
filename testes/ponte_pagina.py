"""
A página da janela (janela/interface/index.html) num Chromium sem tela, falando com o Python DE
VERDADE (a classe Api do app_janela), como o pywebview faz -- só que sem o pywebview:

    window.pywebview.api.<nome>(...)  ->  Api().<nome>(...)          (expose_binding)
    ponte.janela.run_js(...)           ->  lba.receber([eventos])     (bombear)

Esta classe faz o papel da janela do pywebview para a Ponte do app_janela (run_js) e para as
caixas de abrir/salvar arquivo (create_file_dialog, que devolve o que o teste deixou em
`dialogos`). Os eventos chegam de outras linhas de execução (a Ponte, as automações); como a API
síncrona do Playwright só pode ser usada na linha que a criou, eles ficam numa fila e são
entregues à página por esperar()/bombear(), na linha do teste. Usado por testes/cadastro e
testes/anexar.
"""
import json
import os
import queue
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = "file:///" + os.path.join(RAIZ, "janela", "interface", "index.html").replace(os.sep, "/").lstrip("/")

_PONTE_JS = """
window.pywebview = { api: new Proxy({}, { get: (_alvo, nome) =>
  (nome === 'then' ? undefined : (...args) => window.pyApi(String(nome), args)) }) };
"""


class PaginaComPython:
    def __init__(self, playwright, app_janela, largura=1280, altura=900):
        self.A = app_janela
        self.api = app_janela.Api()
        self.fila: "queue.Queue" = queue.Queue()
        self.eventos: list = []
        self.dialogos: list = []  # respostas das caixas de abrir/salvar arquivo, na ordem
        self._janela_original = app_janela.ponte.janela
        app_janela.ponte.janela = self
        self.erros_js: list = []
        # Um Playwright (abre um Chromium só para a página) ou um navegador já aberto (o dos testes).
        self._proprio = hasattr(playwright, "chromium")
        self.navegador = playwright.chromium.launch() if self._proprio else playwright
        self.contexto = self.navegador.new_context(viewport={"width": largura, "height": altura})
        self.page = self.contexto.new_page()
        self.page.on("pageerror", lambda erro: self.erros_js.append(str(erro)))
        self.page.expose_binding("pyApi", self._chamar)
        self.page.add_init_script(_PONTE_JS)
        self.page.goto(PAGINA)
        self.page.wait_for_function("window.lba && window.lbaModulos")

    def _chamar(self, _origem, nome, argumentos):
        resultado = getattr(self.api, nome)(*argumentos)
        return json.loads(json.dumps(resultado, default=str))  # o que o pywebview mandaria ao JS

    # ---- o papel da janela do pywebview

    def run_js(self, codigo: str) -> None:
        """A Ponte manda 'window.lba && lba.receber([...])': os eventos vão para a fila."""
        inicio = codigo.index("lba.receber(") + len("lba.receber(")
        for evento in json.loads(codigo[inicio:codigo.rindex(")")]):
            self.fila.put(evento)

    def create_file_dialog(self, *_args, **_kwargs):
        return self.dialogos.pop(0) if self.dialogos else None

    # ---- o lado do teste

    def bombear(self) -> None:
        lote = []
        while not self.fila.empty():
            lote.append(self.fila.get_nowait())
        if lote:
            self.eventos.extend(lote)
            self.page.evaluate("eventos => lba.receber(eventos)", lote)

    def esperar(self, condicao, segundos=30.0, mensagem=""):
        """Espera `condicao()` (função Python) ou a expressão JS dar verdadeiro, entregando os eventos."""
        limite = time.time() + segundos
        while True:
            self.bombear()
            valor = condicao() if callable(condicao) else self.page.evaluate(condicao)
            if valor:
                return valor
            if time.time() > limite:
                raise AssertionError(f"Esperei {segundos}s e não aconteceu: {mensagem or condicao}\n"
                                     f"erros na página: {self.erros_js}\núltimos eventos: {[e.get('tipo') for e in self.eventos[-12:]]}")
            self.page.wait_for_timeout(100)

    def texto(self, seletor: str) -> str:
        return self.page.locator(seletor).first.inner_text()

    def fechar(self) -> None:
        self.A.ponte.janela = self._janela_original
        self.contexto.close()
        if self._proprio:
            self.navegador.close()
