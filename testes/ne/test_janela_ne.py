"""
A Nota de Empenho na janela da Central, sem navegador: a porta da página
(Api.ne -> janela/modulo_ne.py) e o que o Trabalhador avisa à página. A
automação em si (SIGEF/SEI) é simulada aqui -- ela é testada nos cenarios.py.

Confere também a separação: a NE só fala por eventos "ne_*", nunca pelos da
tela da OB ("erro", "concluido", "pergunta"...).

    python -m unittest discover -s testes/ne -t .
"""
import builtins
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

# A pasta de dados vai para um lugar temporário ANTES de importar a janela, que
# já abre o registro do dia ali. A janela também troca a saída e o input():
# depois do import, os originais voltam, para não atrapalhar os outros testes.
_PASTA = tempfile.mkdtemp(prefix="janela_ne_")
os.environ["LBA_PASTA_DADOS"] = _PASTA
_saida, _erros, _input = sys.stdout, sys.stderr, builtins.input
import app_janela as A  # noqa: E402
sys.stdout, sys.stderr, builtins.input = _saida, _erros, _input

M = A._modulo_ne()  # janela/modulo_ne.py, já ligado à janela
from automacoes import geral  # noqa: E402

geral._aplicar(2026)  # os números dos testes são de 2026, seja qual for o ano do relógio

PROC = "0029.001947/2026-67"
LISTA = f"{PROC}    2026NE000001\n0029.001948/2026-11    000002\nsem processo 000003\n"
EVENTOS_DA_OB = {"erro", "concluido", "pergunta", "etapa", "resumo", "avisos", "lote_inicio", "lote_item", "lote_fim"}


class Base(unittest.TestCase):
    def setUp(self):
        self.eventos = []
        anotar = lambda tipo, **dados: self.eventos.append((tipo, dados))  # noqa: E731
        for alvo in (M._e, A.ponte):
            p = mock.patch.object(alvo, "emitir", anotar)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._esvaziar_filas)
        self.ne = A.Api().ne

    @staticmethod
    def _esvaziar_filas():
        for fila in (A.trabalhador.comandos, A._respostas):
            while not fila.empty():
                fila.get_nowait()

    def tipos(self):
        return [tipo for tipo, _ in self.eventos]


class TestPorta(Base):
    def test_estado(self):
        e = self.ne("estado")
        self.assertEqual((e["ano"], e["tipo_sei"]), (M.etapa.ANO_SIGEF, "NE - Nota de Empenho"))
        from automacoes.ne import __version__
        self.assertEqual(e["versao"], __version__)

    def test_valida(self):
        r = self.ne("validar", {"processo": "0029001947202667", "ne": "123"})
        self.assertEqual(r["processo"], PROC)
        self.assertEqual(r["ne"], {"ne": "000123", "completa": "2026NE000123"})
        r = self.ne("validar", {"processo": "123", "ne": "2025NE000123"})
        self.assertIsNone(r["processo"])
        self.assertIsNone(r["ne"])  # outro exercício

    def test_processar_recusa_campo_errado(self):
        self.assertEqual(self.ne("processar", {"processo": "1", "ne": "123"}), {"ok": False, "campo": "processo"})
        self.assertEqual(self.ne("processar", {"processo": PROC, "ne": "0"}), {"ok": False, "campo": "ne"})
        self.assertTrue(A.trabalhador.comandos.empty())

    def test_processar_manda_ao_trabalhador(self):
        r = self.ne("processar", {"processo": "0029001947202667", "ne": "2026NE000123"})
        self.assertEqual(r, {"ok": True, "processo": PROC, "ne": "000123", "ne_completa": "2026NE000123"})
        self.assertEqual(A.trabalhador.comandos.get_nowait(),
                         ("ne_processar", {"processo": PROC, "ne": "000123", "nome_arvore": ""}))
        self.ne("processar", {"processo": PROC, "ne": "123", "nome_arvore": "  " + "x" * 60 + " "})
        self.assertEqual(A.trabalhador.comandos.get_nowait()[1]["nome_arvore"], "x" * 50)  # limite do SEI

    def test_lista_e_lote(self):
        r = self.ne("ler_texto", {"texto": LISTA})
        self.assertEqual([i["ne"] for i in r["itens"]], ["000001", "000002", "000003"])
        self.assertEqual([bool(i["erro"]) for i in r["itens"]], [False, False, True])
        self.assertEqual(self.ne("processar_lote"), {"ok": True, "quantidade": 2})
        comando, argumentos = A.trabalhador.comandos.get_nowait()
        self.assertEqual(comando, "ne_lote")
        self.assertEqual([i.ne for i in argumentos["itens"]], ["000001", "000002"])
        self.assertEqual(self.ne("processar_lote", {"linhas": [2]})["quantidade"], 1)  # tentar de novo só a linha 2

    def test_lista_sem_linha_valida(self):
        self.ne("ler_texto", {"texto": "nada aqui 1"})
        self.assertFalse(self.ne("processar_lote")["ok"])

    def test_lista_da_ob_nao_e_tocada(self):
        api = A.Api()
        api.ler_lote_texto(f"{PROC} 2026OB136475", "regularizacao")
        self.ne("ler_texto", {"texto": LISTA})
        self.assertEqual([i.ob for i in api._itens], ["2026OB136475"])

    def test_acao_desconhecida(self):
        self.assertFalse(self.ne("nao_existe")["ok"])

    def test_concluir_conferencia_responde(self):
        self.ne("concluir_conferencia")
        self.assertEqual(A._respostas.get_nowait(), "")

    def test_relatorio(self):
        caminho = os.path.join(_PASTA, "rel.html")
        with mock.patch.object(M.relatorio, "gerar", return_value=caminho) as gerar, \
                mock.patch.object(M.os, "startfile", create=True):
            r = self.ne("relatorio", {"de": "2026-10-01", "ate": "2026-10-31", "minutos_manual": "12"})
        self.assertEqual(r, {"ok": True, "caminho": caminho})
        gerar.assert_called_once_with(date(2026, 10, 1), date(2026, 10, 31), 12.0)
        self.assertEqual(self.ne("opcoes_relatorio")["minutos_manual"], 12.0)
        self.assertIn("NE", self.ne("relatorio", {"de": "2026-10-01", "ate": "2026-10-31", "minutos_manual": "0"})["erro"])

    def test_relatorio_com_datas_trocadas(self):
        with mock.patch.object(M.relatorio, "ler_metricas_ne", return_value=[]):
            caminho = M.relatorio.gerar(date(2026, 10, 31), date(2026, 10, 1), 15, destino=os.path.join(_PASTA, "r.html"))
        self.assertIn("01/10/2026", open(caminho, encoding="utf-8").read())


class TestTrabalhador(Base):
    def setUp(self):
        super().setUp()
        self.t = A.Trabalhador()
        # Sem Chrome de verdade: não conecta, e no "sair" não solta (para olhar a aba depois).
        for nome in ("_garantir_conexao", "_soltar"):
            p = mock.patch.object(self.t, nome, lambda: None)
            p.start()
            self.addCleanup(p.stop)

    def rodar(self, *comandos):
        for comando in comandos:
            self.t.comandos.put(comando)
        self.t.comandos.put(("sair", {}))
        self.t.run()

    def test_uma_ne_ate_a_conferencia(self):
        dados = {"ne": "000001", "pasta_processo": _PASTA, "arquivos": [], "avisos_download": []}

        def processar_falso(context, aba, processo, ne, ao_etapa=None, nome_arvore=""):
            self.assertEqual(nome_arvore, "Empenho 12")
            ao_etapa("sigef")
            ao_etapa("sei", dados)
            return "aba nova", ["um aviso"], {"sigef": 1.0, "sei": 2.0, "total": 3.0}

        A._respostas.put("")  # a pessoa conclui a conferência
        with mock.patch.object(M.etapa, "processar_ne", processar_falso):
            self.rodar(("ne_processar", {"processo": PROC, "ne": "000001", "nome_arvore": "Empenho 12"}))

        self.assertEqual(self.tipos(), ["ne_etapa", "ne_etapa", "ne_resumo", "ne_conferencia", "ne_concluido"])
        self.assertEqual(self.eventos[3][1]["avisos"], ["um aviso"])
        self.assertEqual(self.eventos[4][1]["tempos"]["total"], 3.0)
        self.assertEqual(self.t.aba_sigef, "aba nova")

    def test_erro_vai_para_a_tela_da_ne(self):
        with mock.patch.object(M.etapa, "processar_ne", side_effect=SystemExit("boom de teste")):
            self.rodar(("ne_processar", {"processo": PROC, "ne": "000001"}))
        self.assertEqual(self.tipos(), ["ne_erro"])
        self.assertEqual(self.eventos[0][1]["mensagem"], "boom de teste")
        self.assertFalse(EVENTOS_DA_OB & set(self.tipos()))

    def test_lote(self):
        itens = M.lote.ler_texto_ne(LISTA)

        def lote_falso(context, aba, validos, deve_parar=None, ao_etapa=None):
            resultados = [M.lote.ResultadoNE(i) for i in validos]
            ao_etapa(0, "sigef", resultados)
            ao_etapa(0, "sigef", resultados)  # tentativa repetida depois de uma queda
            ao_etapa(0, "sei", resultados)
            resultados[0].estado = "ok"
            ao_etapa(0, "fim", resultados)
            return resultados, "lote.csv"

        with mock.patch.object(M.lote, "processar_lote_ne", lote_falso):
            self.rodar(("ne_lote", {"itens": itens}))

        self.assertEqual(self.tipos(), ["ne_lote_inicio", "ne_lote_item", "ne_etapa", "ne_etapa", "ne_etapa",
                                        "ne_lote_item", "ne_lote_fim"])
        self.assertEqual(len(self.eventos[0][1]["itens"]), 2)  # só as válidas
        fim = self.eventos[-1][1]
        self.assertEqual(fim["relatorio"], "lote.csv")
        self.assertEqual([r["estado"] for r in fim["resultados"]], ["ok", "pendente"])

    def test_nao_roda_junto_com_outra_automacao(self):
        self.assertTrue(A.modulos_janela.USO_DO_CHROME.acquire(blocking=False))
        self.addCleanup(A.modulos_janela.USO_DO_CHROME.release)
        with mock.patch.object(M.etapa, "processar_ne") as processar:
            self.rodar(("ne_processar", {"processo": PROC, "ne": "000001"}))
        processar.assert_not_called()
        self.assertEqual(self.tipos(), ["ne_erro"])
        self.assertIn("usando o Chrome", self.eventos[0][1]["mensagem"])

    def test_conectar_avisa_a_ne(self):
        with mock.patch.object(self.t, "_conectar", lambda: None):
            self.rodar(("ne_conectar", {}))
        self.assertEqual(self.tipos(), ["ne_conectado"])

    def test_janela_fechada_na_conferencia_encerra(self):
        A._respostas.put(None)  # o app_janela põe None quando a janela fecha
        with mock.patch.object(M.etapa, "processar_ne", return_value=("aba", [], {"total": 1})):
            self.rodar(("ne_processar", {"processo": PROC, "ne": "000001"}), ("ne_conectar", {}))
        self.assertEqual(self.tipos(), ["ne_conferencia"])  # parou: não concluiu nem rodou o resto


if __name__ == "__main__":
    unittest.main()
