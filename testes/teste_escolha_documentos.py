"""
Testes offline da escolha de documentos (caixas CE / NL / PP / OB do
passo 3). Não abre navegador, não fala com SIGEF nem SEI.

    python testes/teste_escolha_documentos.py

O download (etapa_listar_baixar) roda DE VERDADE contra um SIGEF de
mentira, que registra cada janela aberta e cada "Imprimir" clicado --
inclusive o desvio que o SIGEF faz na janela da PP quando a CE fecha.
Assim dá para conferir, para cada combinação de caixas, que o caminho
entre as telas continua o mesmo e que só o que foi marcado é baixado.

A anexação no SEI (etapa_sei2) roda com o _anexar_documento trocado por
um registro: confere o que seria anexado, e em que ordem.
"""
import itertools
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager

PASTA_AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PASTA_AQUI)

# Os módulos são carregados só na hora de rodar (setUpModule) e devolvidos
# no fim: outro teste da pasta (testes_divisao.py) põe um substituto do
# etapa_listar_baixar no lugar, e um não pode atrapalhar o outro.
_guardados = {}
baixar = sei = docs_mod = None
_PASTA_DADOS = None

# ------------------------------------------------- o SIGEF de mentira

OB = "2026OB136475"
# PP -> (CE, NL). A 2ª repete a CE da 1ª; a 3ª é um pagamento devolvido.
PPS = {
    "2026PP000001": ("2026CE000010", "2026NL000100"),
    "2026PP000002": ("2026CE000010", "2026NL000200"),
    "2026PP000003": ("", ""),
}


class _Download:
    def save_as(self, caminho):
        with open(caminho, "wb") as arquivo:
            arquivo.write(b"%PDF-falso")


class _Info:
    value = None


class _Locator:
    def __init__(self, pagina, seletor, filtro=None, indice=None):
        self.pagina, self.seletor, self.filtro, self.indice = pagina, seletor, filtro, indice

    # encadeamento
    def locator(self, sub):
        return _Locator(self.pagina, f"{self.seletor} >> {sub}", self.filtro, self.indice)

    def filter(self, has_text=None):
        return _Locator(self.pagina, self.seletor, has_text, self.indice)

    @property
    def first(self):
        return self

    def nth(self, i):
        return _Locator(self.pagina, self.seletor, self.filtro, i)

    # ações
    def fill(self, *a, **k):
        pass

    def select_option(self, *a, **k):
        pass

    def wait_for(self, *a, **k):
        pass

    def click(self, *a, **k):
        self.pagina.ctx.ultimo_clique = self
        if "Gerar Relatório" in self.seletor:
            self.pagina.ctx.registrar("imprimir", self.pagina.nome)

    # leitura
    def _vinculado(self):
        ce, nl = PPS.get(self.pagina.pp, ("", ""))
        if "txtNuDespesaCertificada" in self.seletor:
            return ce
        if "txtNotaLancamento" in self.seletor:
            return nl
        return None

    def count(self):
        valor = self._vinculado()
        if valor is not None:
            return 1 if valor else 0
        if "grdPreparacaoPagamento" in self.seletor and self.filtro is None:
            return len(PPS)
        return 1

    def input_value(self, *a, **k):
        valor = self._vinculado()
        return valor if valor is not None else "1"

    def inner_text(self, *a, **k):
        if "dtgListarOrdemBancaria" in self.seletor:
            return OB
        if "ancestor::tr" in self.seletor:
            return f"{list(PPS)[self.indice]}  12.345.678/0001-90  1.000,00"
        if "grdPreparacaoPagamento" in self.seletor and self.indice is not None:
            return list(PPS)[self.indice]
        return ""

    def all_inner_texts(self):
        return [OB]


class _Pagina:
    def __init__(self, ctx, nome, url, pp=None):
        self.ctx, self.nome, self.url, self.pp = ctx, nome, url, pp
        self.fechada = False
        self.frames = []

    def locator(self, seletor):
        return _Locator(self, seletor)

    def goto(self, url, **k):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass

    def bring_to_front(self):
        pass

    def is_closed(self):
        return self.fechada

    def close(self):
        self.fechada = True
        self.ctx.registrar("fechar", self.nome)
        # O desvio real do SIGEF: fechar a CE leva a janela da PP para o
        # "Detalhar Ordem Bancária". O código tem que voltar sozinho.
        if self.nome == "CE":
            for pagina in self.ctx.pages:
                if pagina.pp and not pagina.fechada:
                    pagina.url = "http://sigef/FIN/" + baixar.TRECHO_URL_DETALHAR_OB


class _Contexto:
    def __init__(self):
        self.pages = []
        self.eventos = []
        self.ultimo_clique = None
        self.browser = types.SimpleNamespace(is_connected=lambda: True)

    def registrar(self, *evento):
        self.eventos.append(evento)

    def _nova_pagina(self):
        clique = self.ultimo_clique
        sel = clique.seletor
        if "Gerar Relatório" in sel:
            pagina = _Pagina(self, "formato:" + clique.pagina.nome, "http://sigef/formato")
        elif "dtgListarOrdemBancaria" in sel:
            pagina = _Pagina(self, "OB-detalhe", "http://sigef/FIN/" + baixar.TRECHO_URL_DETALHAR_OB)
        elif "grdPreparacaoPagamento" in sel:
            pp = next(p for p in PPS if clique.filtro.search(p))
            pagina = _Pagina(self, "PP " + pp, f"http://sigef/FIN/{baixar.TRECHO_URL_DETALHAR_PP}?pp={pp}", pp=pp)
        elif "txtNuDespesaCertificada" in sel:
            pagina = _Pagina(self, "CE", "http://sigef/ce")
        else:
            raise AssertionError(f"clique que não abre janela nenhuma: {sel}")
        self.pages.append(pagina)
        self.registrar("abrir", pagina.nome)
        return pagina

    @contextmanager
    def expect_page(self, **k):
        info = _Info()
        yield info
        info.value = self._nova_pagina()

    @contextmanager
    def expect_event(self, nome, **k):
        info = _Info()
        yield info
        self.registrar("download", self.ultimo_clique.pagina.nome)
        info.value = _Download()


def _simular_download(documentos, reaproveitar=False):
    ctx = _Contexto()
    aba = _Pagina(ctx, "principal", baixar.URL_SIGEF_LISTAR_OB)
    ctx.pages.append(aba)
    dados = baixar.baixar_documentos(
        ctx, aba, "0029.001947/2026-67", OB, documentos=documentos, reaproveitar=reaproveitar
    )
    return dados, ctx.eventos


def _baixados(dados):
    """Que tipos o pacote trouxe, e quantos documentos de cada."""
    lanc = dados["lancamentos"]
    return {
        "CE": len([1 for _n, a in dados["grupos_ce"] if a]),
        "NL": len({tuple(i["arquivos_nl"]) for i in lanc if i["arquivos_nl"]}),
        "PP": len([1 for i in lanc if i["arquivos_pp"]]),
        "OB": 1 if dados["arquivos_ob"] else 0,
    }


ESPERADO_TUDO = {"CE": 1, "NL": 2, "PP": 3, "OB": 1}


def setUpModule():
    global baixar, sei, docs_mod, _PASTA_DADOS
    for nome in list(sys.modules):
        if nome == "automacoes" or nome.startswith(("automacoes.", "playwright", "pymupdf")):
            _guardados[nome] = sys.modules.pop(nome)
    sys.path.insert(0, RAIZ)
    _PASTA_DADOS = tempfile.mkdtemp(prefix="teste_docs_")
    os.environ["LBA_PASTA_DADOS"] = _PASTA_DADOS

    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        api = types.ModuleType("playwright.sync_api")

        class Erro(Exception):
            pass

        class Tempo(Erro):
            pass

        api.Error, api.TimeoutError, api.Page = Erro, Tempo, object
        api.sync_playwright = lambda: None
        sys.modules["playwright"] = types.ModuleType("playwright")
        sys.modules["playwright.sync_api"] = api
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        sys.modules["pymupdf"] = types.ModuleType("pymupdf")

    from automacoes.sigef_sei import documentos as d
    from automacoes.sigef_sei import etapa_listar_baixar as b
    from automacoes.sigef_sei import etapa_sei2 as s

    baixar, sei, docs_mod = b, s, d

    # Fora do navegador: sessão sempre válida, nenhuma janela sobrando,
    # PDF -> "JPG" vira só um arquivo com o nome certo, e a NL (tela
    # própria, que não muda com a escolha) é registrada e "baixada".
    b.garantir_sessao_sigef = lambda context, aba: aba
    b.fechar_janelas_sobrando = lambda context, manter: None

    def pdf_para_jpg(caminho_pdf, pasta, nome_arquivo):
        caminho = os.path.join(pasta, nome_arquivo + ".jpg")
        open(caminho, "wb").close()
        return [caminho]

    b.pdf_para_jpg = pdf_para_jpg

    def baixar_nl(context, aba, pasta, pp, numero_nl):
        context.registrar("imprimir", "NL " + numero_nl)
        return pdf_para_jpg("", pasta, f"Nota de Lançamento - PP {pp}")

    b._baixar_nl = baixar_nl


def tearDownModule():
    for nome in list(sys.modules):
        if nome == "automacoes" or nome.startswith(("automacoes.", "playwright", "pymupdf")):
            del sys.modules[nome]
    sys.modules.update(_guardados)
    os.environ.pop("LBA_PASTA_DADOS", None)
    shutil.rmtree(_PASTA_DADOS, ignore_errors=True)


def _todas_as_escolhas():
    siglas = ("CE", "NL", "PP", "OB")
    for n in range(1, 5):
        yield from itertools.combinations(siglas, n)


class TestaDocumentos(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(docs_mod.normalizar_documentos(None), ("CE", "NL", "PP", "OB"))
        self.assertEqual(docs_mod.normalizar_documentos(["ob", "pp"]), ("PP", "OB"))
        self.assertEqual(docs_mod.normalizar_documentos([]), ("CE", "NL", "PP", "OB"))
        self.assertEqual(docs_mod.descrever(["PP", "OB"]), "PP e OB")
        self.assertEqual(docs_mod.descrever(None), "CE, NL, PP e OB")
        self.assertEqual(docs_mod.descrever(["OB"]), "OB")


class TestaDownload(unittest.TestCase):
    def setUp(self):
        baixar.salvar_sessao(download_completo=False)

    def test_tudo_marcado_baixa_tudo(self):
        dados, eventos = _simular_download(None)
        self.assertEqual(_baixados(dados), ESPERADO_TUDO)
        # A CE repetida é baixada uma vez só, como antes.
        self.assertEqual(eventos.count(("abrir", "CE")), 1)
        self.assertEqual(dados["documentos"], ["CE", "NL", "PP", "OB"])

    def test_cada_escolha_baixa_so_o_marcado(self):
        for escolha in _todas_as_escolhas():
            with self.subTest(escolha=escolha):
                dados, eventos = _simular_download(list(escolha))
                esperado = {k: (v if k in escolha else 0) for k, v in ESPERADO_TUDO.items()}
                self.assertEqual(_baixados(dados), esperado)

                impressos = [quem for tipo, quem in eventos if tipo == "imprimir"]
                self.assertEqual(any(q == "CE" for q in impressos), "CE" in escolha)
                self.assertEqual(any(q.startswith("NL") for q in impressos), "NL" in escolha)
                self.assertEqual(any(q.startswith("PP") for q in impressos), "PP" in escolha)
                self.assertEqual("principal" in impressos, "OB" in escolha)

                # As PPs só deixam de ser abertas quando só a OB foi marcada.
                abertas = [quem for tipo, quem in eventos if tipo == "abrir" and quem.startswith("PP ")]
                self.assertEqual(len(abertas), 0 if escolha == ("OB",) else len(PPS))
                # Toda janela de PP aberta foi fechada (a grade da OB segue usável).
                self.assertEqual(
                    abertas, [quem for tipo, quem in eventos if tipo == "fechar" and quem.startswith("PP ")]
                )
                # Um lançamento por PP, sempre (resumo e sessão no formato de sempre).
                self.assertEqual([i["pp"] for i in dados["lancamentos"]], list(PPS))

    def test_resumo_sem_falta_quando_pp_nao_foi_marcada(self):
        dados, _ = _simular_download(["OB"])
        self.assertTrue(all(i["anexo_baixado"] for i in dados["lancamentos"]))

    def test_reaproveita_so_se_o_anterior_tinha_os_tipos_pedidos(self):
        _simular_download(["PP", "OB"])
        proc = "0029.001947/2026-67"
        self.assertIsNotNone(baixar.download_ja_feito(proc, OB, ["OB"]))
        self.assertIsNotNone(baixar.download_ja_feito(proc, OB, ["PP", "OB"]))
        self.assertIsNone(baixar.download_ja_feito(proc, OB, ["CE", "PP", "OB"]))
        self.assertIsNone(baixar.download_ja_feito(proc, OB, None))

        # Download completo serve para qualquer escolha, filtrado.
        _simular_download(None)
        pronto = baixar.download_ja_feito(proc, OB, ["OB"])
        self.assertEqual(_baixados(pronto), {"CE": 0, "NL": 0, "PP": 0, "OB": 1})
        # ...e não mexe no que está gravado na sessão.
        completo = baixar.download_ja_feito(proc, OB, None)
        self.assertEqual(_baixados(completo), ESPERADO_TUDO)

    def test_sessao_antiga_sem_escolha_vale_tudo(self):
        _simular_download(None)
        sessao = baixar.carregar_sessao()
        sessao.pop("download_documentos")
        with open(baixar.CAMINHO_SESSAO, "w", encoding="utf-8") as arquivo:
            import json
            json.dump(sessao, arquivo)
        self.assertIsNotNone(baixar.download_ja_feito("0029.001947/2026-67", OB, None))


class TestaSei(unittest.TestCase):
    def _anexar(self, documentos):
        baixar.salvar_sessao(download_completo=False)
        dados, _ = _simular_download(None)
        chamadas = []
        originais = (sei._anexar_documento, sei.obter_ou_criar_aba, sei.abrir_processo_sei,
                     sei._aguardar_rede, sei._procurar_lugar)
        sei._anexar_documento = lambda ctx, aba, prog, avisos, chave, *a, **k: chamadas.append(chave)
        sei.obter_ou_criar_aba = lambda *a, **k: types.SimpleNamespace(bring_to_front=lambda: None)
        sei.abrir_processo_sei = lambda *a, **k: None
        sei._aguardar_rede = lambda *a, **k: None
        sei._procurar_lugar = lambda *a, **k: (None, None, None)
        try:
            sei.executar_sei2(None, "0029.001947/2026-67", dados=dados, tipo_ob="OB - x",
                              conferir_no_fim=False, documentos=documentos)
        finally:
            (sei._anexar_documento, sei.obter_ou_criar_aba, sei.abrir_processo_sei,
             sei._aguardar_rede, sei._procurar_lugar) = originais
        return chamadas

    def test_tudo_na_ordem_de_sempre(self):
        self.assertEqual(self._anexar(None), [
            "CE 2026CE000010", "NL 2026PP000001", "NL 2026PP000002",
            "PP 2026PP000001", "PP 2026PP000002", "PP 2026PP000003", "OB",
        ])

    def test_so_pp_e_ob(self):
        self.assertEqual(self._anexar(["PP", "OB"]), [
            "PP 2026PP000001", "PP 2026PP000002", "PP 2026PP000003", "OB",
        ])

    def test_so_ce(self):
        self.assertEqual(self._anexar(["CE"]), ["CE 2026CE000010"])

    def test_marcado_que_a_ob_nao_tem_para_sem_pegar_arquivo_de_outra_ob(self):
        global PPS
        guardado = PPS
        PPS = {"2026PP000003": ("", "")}   # só pagamento devolvido: sem CE
        try:
            baixar.salvar_sessao(download_completo=False)
            dados, _ = _simular_download(["CE"])
            with self.assertRaises(SystemExit):
                sei.executar_sei2(None, "0029.001947/2026-67", dados=dados, tipo_ob="OB - x",
                                  conferir_no_fim=False, documentos=["CE"])
        finally:
            PPS = guardado


if __name__ == "__main__":
    unittest.main(verbosity=2)
