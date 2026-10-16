"""Testa o loop de lotes com o navegador simulado (sem Chrome, DARE ou SEI)."""

import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import terminal as app
from automacoes.dare import armazenamento, config, navegador
from automacoes.dare.modelos import DadosDare


def lote(n: int) -> DadosDare:
    return DadosDare(f"0029.00000{n}/2022-0{n}", "11.222.333/0001-81", "529.982.247-25",
                     "11.222.333/0001-81", "102026", date(2026, 11, 10), "7.273,07")


class FakeContext:
    def __enter__(self):
        return mock.MagicMock()

    def __exit__(self, *args):
        return False


class TestLoteLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        pasta = Path(self.tmp.name)
        patchers = [
            mock.patch.object(config, "PASTA_DADOS", pasta),
            mock.patch.object(config, "ARQ_ULTIMOS", pasta / "ultimos.json"),
            mock.patch.object(config, "ARQ_HISTORICO", pasta / "historico.csv"),
            mock.patch.object(config, "ARQ_LOTE", pasta / "lote.json"),
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(app, "sync_playwright", lambda: FakeContext()),
            mock.patch.object(navegador, "garantir_chrome", lambda: True),
            mock.patch.object(navegador, "conectar", lambda p: (None, mock.MagicMock())),
            mock.patch.object(navegador, "obter_aba", lambda c, h, u: (mock.MagicMock(), False)),
            mock.patch.object(navegador, "garantir_aba", lambda c, atual, h, u: atual),
            mock.patch.object(navegador, "ativar_aba", lambda c, p: None),
            mock.patch.object(navegador, "capturar_erro", lambda c: []),
            mock.patch.object(app.menu, "aguardar_login", lambda: None),
            mock.patch.object(app.menu, "cabecalho_lote", lambda *a: None),
            mock.patch.object(app.menu, "erro", lambda *a: None),
            mock.patch.object(app.menu, "sucesso", lambda *a: None),
            mock.patch.object(app.menu, "info", lambda *a: None),
            mock.patch.object(app.menu, "pausar", lambda *a, **k: None),
            mock.patch.object(app.menu, "resumo_lotes", lambda *a: None),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("DARE_DEBUG", None)
        self.addCleanup(self.tmp.cleanup)
        app._estado["login_confirmado"] = False
        self.processados = []

    def _gerar(self, falhar_dare=(), falhar_sei=(), cancelar=()):
        def gerar_dare(context, page, dados):
            self.processados.append(dados.processo)
            if dados.processo in cancelar:
                raise KeyboardInterrupt
            if dados.processo in falhar_dare:
                raise RuntimeError("DARE quebrou")
            return Path(f"{dados.processo[-7:-3]}.pdf"), "FULANO"

        def anexar_pdf(context, page_sei, dados, pdf):
            if dados.processo in falhar_sei:
                raise RuntimeError("SEI quebrou")
            return page_sei

        return (mock.patch.object(app.dare, "gerar_dare", gerar_dare),
                mock.patch.object(app.sei, "anexar_pdf", anexar_pdf))

    def _rodar(self, lotes, **kw):
        a, b = self._gerar(**kw)
        with a, b:
            return app.executar_lotes(lotes)

    def status_historico(self):
        return [l["status"] for l in reversed(armazenamento.ler_historico(50))]

    def test_todos_com_sucesso_em_ordem(self):
        lotes = [lote(1), lote(2), lote(3)]
        resultados, interrompido = self._rodar(lotes)
        self.assertFalse(interrompido)
        self.assertEqual([r.sucesso for r in resultados], [True, True, True])
        self.assertEqual(self.processados, [l.processo for l in lotes])
        self.assertEqual(self.status_historico(), ["SUCESSO"] * 3)

    def test_falha_no_meio_nao_para_o_loop(self):
        lotes = [lote(1), lote(2), lote(3)]
        resultados, _ = self._rodar(lotes, falhar_dare={lotes[1].processo})
        self.assertEqual([r.sucesso for r in resultados], [True, False, True])
        self.assertEqual(self.processados, [l.processo for l in lotes])  # o 3º rodou
        self.assertEqual(self.status_historico(), ["SUCESSO", "ERRO", "SUCESSO"])
        self.assertIn("Lote 2/3", armazenamento.ler_historico()[1]["observacao"])

    def test_falha_no_sei_guarda_o_pdf_e_segue(self):
        lotes = [lote(1), lote(2)]
        resultados, _ = self._rodar(lotes, falhar_sei={lotes[0].processo})
        self.assertEqual([r.sucesso for r in resultados], [False, True])
        self.assertTrue(resultados[0].pdf)  # o DARE foi gerado, só o anexo falhou

    def test_ctrl_c_interrompe_e_deixa_o_resto(self):
        lotes = [lote(1), lote(2), lote(3)]
        resultados, interrompido = self._rodar(lotes, cancelar={lotes[1].processo})
        self.assertTrue(interrompido)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(self.status_historico(), ["SUCESSO", "CANCELADO"])

    def test_chrome_ausente_marca_todos_com_erro(self):
        def sem_chrome(p):
            raise navegador.ChromeNaoEncontrado("sem chrome")

        with mock.patch.object(navegador, "conectar", sem_chrome):
            resultados, interrompido = self._rodar([lote(1), lote(2)])
        self.assertFalse(interrompido)
        self.assertEqual([r.sucesso for r in resultados], [False, False])
        self.assertIn("ChromeNaoEncontrado", resultados[0].erro)

    def test_lancamento_unico_e_lote_de_tamanho_1(self):
        resultados, _ = self._rodar([lote(1)])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(armazenamento.ler_historico()[0]["observacao"], "")  # sem rótulo de lote

    def test_login_so_e_pedido_uma_vez(self):
        chamadas = []
        with mock.patch.object(app.menu, "aguardar_login", lambda: chamadas.append(1)):
            self._rodar([lote(1)])
            self._rodar([lote(2)])
        self.assertEqual(len(chamadas), 1)


class TestRodarLotes(unittest.TestCase):
    """Fluxo de pendentes: repetir só os que falharam e guardar o que sobrou."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        pasta = Path(self.tmp.name)
        for nome, valor in (("PASTA_DADOS", pasta), ("ARQ_LOTE", pasta / "lote.json")):
            p = mock.patch.object(config, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        for nome in ("resumo_lotes", "info"):
            p = mock.patch.object(app.menu, nome, lambda *a, **k: None)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(app.menu, "pausar", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def _com_rodadas(self, rodadas, resposta_retry):
        """rodadas: lista de listas de bool (sucesso) devolvidas por executar_lotes a cada rodada."""
        chamadas = []

        def falso(lotes):
            chamadas.append([l.processo for l in lotes])
            ok = rodadas[len(chamadas) - 1]
            return [app.ResultadoLote(d, s) for d, s in zip(lotes, ok)], False

        with mock.patch.object(app, "executar_lotes", falso), \
                mock.patch.object(app.menu, "sim_nao", lambda *a, **k: resposta_retry):
            app._rodar_lotes([lote(1), lote(2), lote(3)])
        return chamadas

    def test_tudo_ok_limpa_o_pendente(self):
        self._com_rodadas([[True, True, True]], resposta_retry=False)
        self.assertEqual(armazenamento.carregar_lote(), [])

    def test_falhas_sem_repetir_guardam_so_os_falhos(self):
        self._com_rodadas([[True, False, True]], resposta_retry=False)
        self.assertEqual([d.processo for d in armazenamento.carregar_lote()], [lote(2).processo])

    def test_repetir_roda_so_os_que_falharam(self):
        chamadas = self._com_rodadas([[True, False, False], [True, True]], resposta_retry=True)
        self.assertEqual(chamadas[1], [lote(2).processo, lote(3).processo])
        self.assertEqual(armazenamento.carregar_lote(), [])


if __name__ == "__main__":
    unittest.main()
