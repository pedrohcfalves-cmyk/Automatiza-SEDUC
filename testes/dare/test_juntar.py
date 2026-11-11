"""Juntar os PDFs dos DAREs do mesmo processo e anexar um único arquivo no SEI."""

import logging
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import terminal as app_terminal
from automacoes.dare import armazenamento, config, juntar, motor, navegador
from automacoes.dare.modelos import DadosDare

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    PdfReader = PdfWriter = None


def lote(processo: str, cpf: str = "52998224725") -> DadosDare:
    return DadosDare(processo, "11222333000181", cpf, "11222333000181", "102026",
                     date(2026, 11, 10), "100,00")


def criar_pdf(caminho: Path, paginas: int = 1) -> Path:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=200, height=200)
    with open(caminho, "wb") as f:
        escritor.write(f)
    return caminho


A, B = "0029.000001/2022-01", "0029.000002/2022-02"


class TestAgrupar(unittest.TestCase):
    def test_agrupa_na_ordem_em_que_o_processo_aparece(self):
        lotes = [lote(A), lote(B), lote("0029000001202201"), lote(B)]
        self.assertEqual(juntar.agrupar_por_processo(lotes), [[0, 2], [1, 3]])
        ordenados = juntar.ordenar_por_processo(lotes)
        self.assertEqual([juntar.chave_processo(d.processo) for d in ordenados],
                         ["0029000001202201"] * 2 + ["0029000002202202"] * 2)
        self.assertEqual(juntar.ordenar_por_processo(ordenados), ordenados)  # idempotente

    def test_lista_vazia(self):
        self.assertEqual(juntar.agrupar_por_processo([]), [])


@unittest.skipIf(PdfWriter is None, "pypdf ausente")
class TestJuntarPdfs(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        p = mock.patch.object(config, "PASTA_PDF", self.pasta)
        p.start()
        self.addCleanup(p.stop)

    def test_junta_na_ordem_e_mantem_os_originais(self):
        pdfs = [criar_pdf(self.pasta / "a.pdf", 1), criar_pdf(self.pasta / "b.pdf", 2)]
        anexos = juntar.preparar_anexos(pdfs, A)
        self.assertEqual(len(anexos), 1)
        self.assertTrue(anexos[0].name.startswith("DARE_JUNTADO_0029000001202201_2-DAREs_"))
        self.assertEqual(len(PdfReader(str(anexos[0])).pages), 3)
        self.assertTrue(all(p.exists() for p in pdfs))
        self.assertEqual(list(self.pasta.glob("*.tmp")), [])

    def test_um_pdf_so_nao_junta(self):
        pdf = criar_pdf(self.pasta / "a.pdf")
        self.assertEqual(juntar.preparar_anexos([pdf], A), [pdf])
        self.assertEqual(len(list(self.pasta.glob("DARE_JUNTADO_*"))), 0)

    def test_pdf_ilegivel_anexa_um_a_um(self):
        ruim = self.pasta / "ruim.pdf"
        ruim.write_bytes(b"isto nao e um pdf")
        pdfs = [criar_pdf(self.pasta / "a.pdf"), ruim]
        with self.assertLogs("dare.juntar", logging.WARNING):
            self.assertEqual(juntar.preparar_anexos(pdfs, A), pdfs)
        self.assertEqual(list(self.pasta.glob("DARE_JUNTADO_*")), [])

    def test_sem_pypdf_anexa_um_a_um(self):
        pdfs = [self.pasta / "a.pdf", self.pasta / "b.pdf"]
        with mock.patch.object(juntar, "PdfWriter", None), self.assertLogs("dare.juntar", logging.WARNING):
            self.assertEqual(juntar.preparar_anexos(pdfs, A), pdfs)


class FakePW:
    def __enter__(self):
        return mock.MagicMock()

    def __exit__(self, *a):
        return False


@unittest.skipIf(PdfWriter is None, "pypdf ausente")
class TestFluxoJuntado(unittest.TestCase):
    """Janela (motor) e terminal: DAREs do mesmo processo -> um anexo só no SEI."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pasta = Path(self.tmp.name)
        self.pasta = pasta
        patches = [
            mock.patch.object(config, "PASTA_DADOS", pasta),
            mock.patch.object(config, "PASTA_PDF", pasta),
            mock.patch.object(config, "ARQ_ULTIMOS", pasta / "u.json"),
            mock.patch.object(config, "ARQ_HISTORICO", pasta / "h.csv"),
            mock.patch.object(config, "ARQ_LOTE", pasta / "l.json"),
            mock.patch.object(config, "ARQ_DESEMPENHO", pasta / "d.csv"),
            mock.patch.object(motor, "sync_playwright", lambda: FakePW()),
            mock.patch.object(app_terminal, "sync_playwright", lambda: FakePW()),
            mock.patch.object(navegador, "garantir_chrome", lambda: True),
            mock.patch.object(navegador, "conectar", lambda p: (None, mock.MagicMock())),
            mock.patch.object(navegador, "obter_aba", lambda c, h, u: (mock.MagicMock(), False)),
            mock.patch.object(navegador, "garantir_aba", lambda c, a, h, u: a),
            mock.patch.object(navegador, "ativar_aba", lambda c, p: None),
            mock.patch.object(navegador, "capturar_erro", lambda c: []),
        ]
        for nome in ("aguardar_login", "cabecalho_lote", "erro", "sucesso", "info"):
            patches.append(mock.patch.object(app_terminal.menu, nome, lambda *a, **k: None))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        motor._sessao["login_confirmado"] = True
        app_terminal._estado["login_confirmado"] = True
        self.eventos, self.anexados, self.gerados = [], [], []
        self.n = 0

    def _fakes(self, falhar_dare=(), falhar_sei=()):
        def gerar(context, page, dados):
            self.n += 1
            self.gerados.append(dados.cpf)
            if dados.cpf in falhar_dare:
                raise RuntimeError("DARE quebrou")
            return criar_pdf(self.pasta / f"dare{self.n}.pdf"), f"SERVIDOR {self.n}"

        def anexar(context, page_sei, dados, pdf):
            self.anexados.append((dados.processo, Path(pdf)))
            if dados.processo in falhar_sei:
                raise RuntimeError("SEI quebrou")
            return page_sei

        return mock.patch.object(motor.dare, "gerar_dare", gerar), mock.patch.object(motor.sei, "anexar_pdf", anexar)

    def _motor(self, lotes, **kw):
        a, b = self._fakes(**kw)
        with a, b:
            return motor.executar(lotes, lambda t, d: self.eventos.append((t, d)), motor.Controle())

    def _terminal(self, lotes, **kw):
        a, b = self._fakes(**kw)
        with a, b:
            return app_terminal.executar_lotes(lotes)

    def test_motor_junta_por_processo_e_anexa_uma_vez(self):
        lotes = [lote(A, "1"), lote(B, "2"), lote(A, "3")]
        resultados, interrompido = self._motor(lotes)
        self.assertFalse(interrompido)
        self.assertEqual(self.gerados, ["1", "3", "2"])  # os do processo A primeiro
        self.assertEqual(len(self.anexados), 2)  # um anexo por processo
        processo, arquivo = self.anexados[0]
        self.assertEqual(processo, A)
        self.assertTrue(arquivo.name.startswith("DARE_JUNTADO_"))
        self.assertEqual(len(PdfReader(str(arquivo)).pages), 2)
        self.assertEqual(self.anexados[1][1].name, "dare3.pdf")  # processo B: PDF próprio
        self.assertTrue(all(r.sucesso for r in resultados))
        self.assertEqual(armazenamento.carregar_lote(), [])
        tipos = [t for t, _ in self.eventos]
        self.assertEqual(tipos.count("lote_pdf"), 3)
        self.assertEqual(tipos.count("sei_inicio"), 2)
        self.assertEqual(tipos.count("lote_fim"), 3)
        historico = armazenamento.ler_historico(10)
        self.assertTrue(any("anexado junto com outros 1 DARE(s)" in h["observacao"] for h in historico))

    def test_motor_falha_no_sei_deixa_o_processo_pendente(self):
        lotes = [lote(A, "1"), lote(A, "2"), lote(B, "3")]
        resultados, _ = self._motor(lotes, falhar_sei={A})
        self.assertEqual([r.sucesso for r in resultados], [False, False, True])
        self.assertTrue(all(r.pdf for r in resultados[:2]))  # DAREs gerados, não anexados
        self.assertEqual([d.cpf for d in armazenamento.carregar_lote()], ["1", "2"])

    def test_motor_dare_com_erro_fica_fora_do_juntado(self):
        lotes = [lote(A, "1"), lote(A, "2"), lote(A, "3")]
        resultados, _ = self._motor(lotes, falhar_dare={"2"})
        self.assertEqual([r.sucesso for r in resultados], [True, False, True])
        self.assertEqual(len(self.anexados), 1)
        self.assertEqual(len(PdfReader(str(self.anexados[0][1])).pages), 2)
        self.assertEqual([d.cpf for d in armazenamento.carregar_lote()], ["2"])

    def test_motor_parar_anexa_os_ja_gerados(self):
        controle = motor.Controle()

        def emitir(tipo, dados):
            self.eventos.append((tipo, dados))
            if tipo == "lote_pdf" and dados["indice"] == 1:
                controle.cancelar.set()

        a, b = self._fakes()
        with a, b:
            resultados, interrompido = motor.executar([lote(A, "1"), lote(A, "2"), lote(B, "3")], emitir, controle)
        self.assertTrue(interrompido)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(self.anexados), 1)  # o DARE já gerado foi anexado
        self.assertEqual([d.cpf for d in armazenamento.carregar_lote()], ["2", "3"])

    def test_terminal_junta_por_processo(self):
        lotes = [lote(A, "1"), lote(B, "2"), lote(A, "3")]
        resultados, interrompido = self._terminal(lotes)
        self.assertFalse(interrompido)
        self.assertEqual([r.dados.cpf for r in resultados], ["1", "3", "2"])
        self.assertTrue(all(r.sucesso for r in resultados))
        self.assertEqual(len(self.anexados), 2)
        self.assertTrue(self.anexados[0][1].name.startswith("DARE_JUNTADO_"))

    def test_terminal_falha_no_sei_marca_o_processo_todo(self):
        resultados, _ = self._terminal([lote(A, "1"), lote(A, "2"), lote(B, "3")], falhar_sei={A})
        self.assertEqual([r.sucesso for r in resultados], [False, False, True])
        self.assertIn("SEI quebrou", resultados[0].erro)


if __name__ == "__main__":
    unittest.main()
