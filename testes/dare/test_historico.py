"""registrar_historico: falha de disco/arquivo aberto no Excel não pode derrubar o lote."""

import builtins
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import armazenamento, config
from automacoes.dare.modelos import DadosDare

DADOS = DadosDare("0012.123456/2026-12", "11.222.333/0001-81", "529.982.247-25",
                  "11.222.333/0001-81", "102026", date(2026, 11, 10), "100,00")


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hist = Path(self.tmp.name) / "historico.csv"
        self.reserva = Path(self.tmp.name) / "historico_reserva.csv"
        for nome, valor in (("ARQ_HISTORICO", self.hist), ("PASTA_DADOS", Path(self.tmp.name))):
            p = mock.patch.object(config, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def _open_que_falha_em(self, *nomes):
        original = builtins.open

        def abrir(caminho, *args, **kwargs):
            if Path(str(caminho)).name in nomes:
                raise PermissionError(13, "aberto no Excel", str(caminho))
            return original(caminho, *args, **kwargs)

        return mock.patch("builtins.open", abrir)

    def test_caso_normal_grava_com_cabecalho(self):
        self.assertTrue(armazenamento.registrar_historico(DADOS, "OK", "Fulano", "a.pdf"))
        linhas = self.hist.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(len(linhas), 2)
        self.assertTrue(linhas[0].startswith("data_hora;status;processo"))
        self.assertIn("0012.123456/2026-12", linhas[1])

    def test_principal_bloqueado_nao_lanca_e_vai_para_o_reserva(self):
        with self._open_que_falha_em("historico.csv"):
            self.assertFalse(armazenamento.registrar_historico(DADOS, "OK", "Fulano", "a.pdf"))
        linhas = self.reserva.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(len(linhas), 2)  # cabeçalho + a linha que não coube no principal
        self.assertIn("0012.123456/2026-12", linhas[1])

    def test_principal_e_reserva_bloqueados_nao_lanca(self):
        with self._open_que_falha_em("historico.csv", "historico_reserva.csv"):
            self.assertFalse(armazenamento.registrar_historico(DADOS, "ERRO"))


if __name__ == "__main__":
    unittest.main()
