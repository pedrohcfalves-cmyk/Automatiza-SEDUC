"""Motor da janela: loop de lotes em thread, login, cancelamento e medição das etapas."""

import logging
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import armazenamento, config, desempenho, motor, navegador
from automacoes.dare.modelos import DadosDare


def lote(n: int, origem: str = "") -> DadosDare:
    return DadosDare(f"0029.00000{n}/2022-0{n}", "11222333000181", "52998224725",
                     "11222333000181", "102026", date(2026, 11, 10), "100,00", origem)


class FakePW:
    def __enter__(self):
        return mock.MagicMock()

    def __exit__(self, *a):
        return False


class TestMotor(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        pasta = Path(self.tmp.name)
        patches = [
            mock.patch.object(config, "PASTA_DADOS", pasta),
            mock.patch.object(config, "ARQ_ULTIMOS", pasta / "u.json"),
            mock.patch.object(config, "ARQ_HISTORICO", pasta / "h.csv"),
            mock.patch.object(config, "ARQ_LOTE", pasta / "l.json"),
            mock.patch.object(config, "ARQ_DESEMPENHO", pasta / "d.csv"),
            mock.patch.object(motor, "sync_playwright", lambda: FakePW()),
            mock.patch.object(navegador, "garantir_chrome", lambda: True),
            mock.patch.object(navegador, "conectar", lambda p: (None, mock.MagicMock())),
            mock.patch.object(navegador, "obter_aba", lambda c, h, u: (mock.MagicMock(), False)),
            mock.patch.object(navegador, "garantir_aba", lambda c, a, h, u: a),
            mock.patch.object(navegador, "ativar_aba", lambda c, p: None),
            mock.patch.object(navegador, "capturar_erro", lambda c: []),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        motor._sessao["login_confirmado"] = True
        self.eventos = []

    def emitir(self, tipo, dados):
        self.eventos.append((tipo, dados))

    def _rodar(self, lotes, falhar=(), controle=None):
        log_dare = logging.getLogger("dare.dare")
        log_sei = logging.getLogger("dare.sei")

        def gerar(context, page, dados):
            for i in range(1, 6):
                log_dare.info("DARE %d/5 · passo", i)
            if dados.processo in falhar:
                raise RuntimeError("quebrou")
            log_dare.info("PDF salvo em: x.pdf")
            return Path("x.pdf"), "FULANO"

        def anexar(context, page_sei, dados, pdf):
            for i in range(1, 5):
                log_sei.info("SEI %d/4 · passo", i)
            return page_sei

        with mock.patch.object(motor.dare, "gerar_dare", gerar), mock.patch.object(motor.sei, "anexar_pdf", anexar):
            return motor.executar(lotes, self.emitir, controle or motor.Controle())

    def test_todos_com_sucesso_mede_etapas_e_limpa_pendentes(self):
        resultados, interrompido = self._rodar([lote(1), lote(2, "linha 3")])
        self.assertFalse(interrompido)
        self.assertTrue(all(r.sucesso for r in resultados))
        self.assertEqual(armazenamento.carregar_lote(), [])
        linhas = desempenho.carregar_desempenho()
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[1]["origem"], "planilha")
        for chave, _, _ in motor.ETAPAS:
            self.assertIsInstance(linhas[0][f"{chave}_s"], float, chave)
        self.assertIsInstance(linhas[0]["conexao_s"], float)
        self.assertIsNone(linhas[1]["conexao_s"])
        etapas = [d["etapa"] for t, d in self.eventos if t == "etapa"]
        self.assertEqual(etapas[:10], [c for c, _, p in motor.ETAPAS if p])
        self.assertEqual(self.eventos[-1][0], "fim")

    def test_falha_segue_e_guarda_pendente(self):
        resultados, _ = self._rodar([lote(1), lote(2), lote(3)], falhar={lote(2).processo})
        self.assertEqual([r.sucesso for r in resultados], [True, False, True])
        self.assertEqual([d.processo for d in armazenamento.carregar_lote()], [lote(2).processo])
        self.assertIn("quebrou", resultados[1].erro)

    def test_cancelar_antes_do_proximo_lote(self):
        controle = motor.Controle()
        original = self.emitir

        def emitir(tipo, dados):
            original(tipo, dados)
            if tipo == "lote_fim":
                controle.cancelar.set()

        self.emitir = emitir
        resultados, interrompido = self._rodar([lote(1), lote(2), lote(3)], controle=controle)
        self.assertTrue(interrompido)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(armazenamento.carregar_lote()), 2)

    def test_espera_login_e_pode_cancelar(self):
        motor._sessao["login_confirmado"] = False
        controle = motor.Controle()

        def emitir(tipo, dados):
            self.eventos.append((tipo, dados))
            if tipo == "aguardando_login":
                controle.cancelar.set()

        self.emitir = emitir
        resultados, interrompido = self._rodar([lote(1)], controle=controle)
        self.assertTrue(interrompido)
        self.assertEqual(resultados, [])
        self.assertFalse(motor.login_ja_confirmado())

    def test_navegador_nao_abre(self):
        with mock.patch.object(navegador, "garantir_chrome", lambda: False):
            resultados, _ = self._rodar([lote(1), lote(2)])
        self.assertEqual(len(resultados), 2)
        self.assertFalse(any(r.sucesso for r in resultados))
        self.assertTrue(any(t == "erro_geral" for t, _ in self.eventos))


class TestAnalise(unittest.TestCase):
    def test_estatisticas(self):
        e = desempenho.Estatisticas.de([1.0, 2.0, 3.0, 4.0, 10.0])
        self.assertEqual((e.n, e.media, e.mediana, e.minimo, e.maximo), (5, 4.0, 3.0, 1.0, 10.0))
        self.assertAlmostEqual(e.p95, 8.8)
        self.assertEqual(desempenho.Estatisticas.de([]).n, 0)
        self.assertEqual(desempenho.percentil([5.0], 95), 5.0)

    def test_analise_usa_so_sucessos(self):
        linhas = [
            {"status": "SUCESSO", "execucao": "a", "total_s": 10.0, "dare_s": 7.0, "sei_s": 3.0,
             "conexao_s": 2.0, "dare_5_s": 5.0, "sei_1_s": 1.0},
            {"status": "SUCESSO", "execucao": "a", "total_s": 20.0, "dare_s": 15.0, "sei_s": 5.0,
             "conexao_s": None, "dare_5_s": 12.0, "sei_1_s": 1.0},
            {"status": "ERRO", "execucao": "b", "total_s": 99.0, "dare_s": 99.0, "sei_s": None},
        ]
        a = desempenho.analisar_automacao(linhas)
        self.assertEqual((a.lotes, a.sucessos, a.erros, a.execucoes), (3, 2, 1, 2))
        self.assertEqual(a.total.media, 15.0)
        self.assertEqual(a.gargalo, "dare_5")
        self.assertAlmostEqual(a.lotes_por_hora, 240.0)

    def test_relatorio_html(self):
        with TemporaryDirectory() as tmp, mock.patch.object(config, "ARQ_DESEMPENHO", Path(tmp) / "d.csv"):
            caminho = desempenho.gerar_relatorio_html(
                Path(tmp) / "r.html",
                diagnostico=[desempenho.ItemDiagnostico("Sistema", "CPU", "x", desempenho.OK)],
                benchmarks=[desempenho.ResultadoBenchmark("a", "Teste", 12.5, "MB/s")],
            )
            texto = caminho.read_text(encoding="utf-8")
        self.assertIn("Relatório de desempenho", texto)
        self.assertIn("12,50", texto)

    def test_benchmarks_rapidos(self):
        r = desempenho.bench_validacao(duracao=0.05)
        self.assertGreater(r.valor, 0)
        self.assertGreater(desempenho.bench_planilha(linhas=50).valor, 0)
        with TemporaryDirectory() as tmp:
            disco = desempenho.bench_disco(Path(tmp), mb=2)
        self.assertEqual(len(disco), 3)

    def test_monitor(self):
        m = desempenho.Monitor()
        if not m.disponivel:
            self.skipTest("psutil ausente")
        m.amostra()
        a = m.amostra()
        self.assertIn("cpu", a)
        self.assertGreater(a["app_mb"], 0)


if __name__ == "__main__":
    unittest.main()
