import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import armazenamento, config
from automacoes.dare.modelos import DadosDare


def exemplo() -> DadosDare:
    return DadosDare("0012.123456/2026-12", "11.222.333/0001-81", "529.982.247-25",
                     "11.222.333/0001-81", "102026", date(2026, 11, 13), "100,00")


class TestArmazenamento(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        pasta = Path(self.tmp.name)
        for nome, valor in (
            ("PASTA_DADOS", pasta),
            ("ARQ_ULTIMOS", pasta / "ultimos.json"),
            ("ARQ_HISTORICO", pasta / "historico.csv"),
            ("ARQ_LOTE", pasta / "lote.json"),
        ):
            patcher = mock.patch.object(config, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_sem_arquivo(self):
        self.assertIsNone(armazenamento.carregar_ultimos())
        self.assertEqual(armazenamento.ler_historico(), [])

    def test_ida_e_volta(self):
        armazenamento.salvar_ultimos(exemplo())
        self.assertEqual(armazenamento.carregar_ultimos(), exemplo())

    def test_arquivo_corrompido_ou_incompleto(self):
        config.ARQ_ULTIMOS.write_text("{ nao e json", encoding="utf-8")
        self.assertIsNone(armazenamento.carregar_ultimos())
        config.ARQ_ULTIMOS.write_text('{"processo": "x"}', encoding="utf-8")
        self.assertIsNone(armazenamento.carregar_ultimos())

    def test_lote_pendente(self):
        self.assertEqual(armazenamento.carregar_lote(), [])
        armazenamento.salvar_lote([exemplo(), exemplo()])
        self.assertEqual(armazenamento.carregar_lote(), [exemplo(), exemplo()])
        config.ARQ_LOTE.write_text("lixo", encoding="utf-8")
        self.assertEqual(armazenamento.carregar_lote(), [])
        armazenamento.salvar_lote([exemplo()])
        armazenamento.limpar_lote()
        armazenamento.limpar_lote()  # repetir não dá erro
        self.assertEqual(armazenamento.carregar_lote(), [])

    def test_historico(self):
        armazenamento.registrar_historico(exemplo(), "SUCESSO", "FULANO", "a.pdf")
        armazenamento.registrar_historico(exemplo(), "ERRO", observacao="falhou; com ponto e vírgula")
        linhas = armazenamento.ler_historico()
        self.assertEqual([l["status"] for l in linhas], ["ERRO", "SUCESSO"])  # mais recente primeiro
        self.assertEqual(linhas[0]["observacao"], "falhou; com ponto e vírgula")
        self.assertEqual(config.ARQ_HISTORICO.read_bytes().count(b"\xef\xbb\xbf"), 1)  # um só BOM


if __name__ == "__main__":
    unittest.main()
