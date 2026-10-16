"""Modo planilha sem o Excel (openpyxl)."""

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from automacoes.dare import excel_com, planilha, planilha_arquivo


class TestPlanilhaArquivo(unittest.TestCase):
    def test_modelo_criado_e_lido(self):
        with TemporaryDirectory() as tmp:
            destino = planilha_arquivo.criar_modelo(Path(tmp) / "modelo.xlsx")
            pasta = planilha_arquivo.PastaArquivo(destino)
            self.assertEqual(pasta.abas(), ["DARE", "Instruções"])
            tabela = pasta.tabela("DARE")
            linha = planilha.detectar_linha_cabecalho(tabela)
            mapa = planilha.Mapeamento(planilha.sugerir_mapeamento(planilha.ler_cabecalhos(tabela, linha)), linha)
            self.assertEqual(mapa.faltando(), [])
            r = planilha.ler_lotes(tabela, mapa, 2, planilha.ultima_linha_com_dados(tabela, mapa))
            pasta.fechar()
        self.assertEqual(len(r.lotes), 1)
        self.assertEqual(r.lotes[0].cpf, "52998224725")
        self.assertEqual(r.lotes[0].valor, "100,00")

    def test_linhas_ocultas_e_datas(self):
        from openpyxl import Workbook
        with TemporaryDirectory() as tmp:
            wb = Workbook()
            ws = wb.active
            ws.append(["Processo", "CNPJ", "CPF", "CNPJ recolhedor", "Referência", "Vencimento", "Valor"])
            ws.append(["0029.1/2026", "11222333000181", 52998224725, "11222333000181", "10/2026",
                       datetime(2026, 11, 10), 7273.07])
            ws.append(["0029.2/2026", "11222333000181", "52998224725", "11222333000181", "102026", None, None])
            ws.row_dimensions[3].hidden = True
            arq = Path(tmp) / "p.xlsx"
            wb.save(arq)
            pasta = planilha_arquivo.PastaArquivo(arq)
            tabela = pasta.tabela(pasta.abas()[0])
            mapa = planilha.Mapeamento(planilha.sugerir_mapeamento(planilha.ler_cabecalhos(tabela, 1)), 1)
            r = planilha.ler_lotes(tabela, mapa, 2, 3)
            pasta.fechar()
        self.assertEqual(r.ocultas, 1)
        self.assertEqual(r.lotes[0].valor, "7.273,07")
        self.assertEqual(r.lotes[0].vencimento.isoformat(), "2026-11-10")

    def test_formato_nao_suportado(self):
        with TemporaryDirectory() as tmp:
            arq = Path(tmp) / "x.xls"
            arq.write_bytes(b"x")
            with self.assertRaises(excel_com.ExcelIndisponivel):
                planilha_arquivo.PastaArquivo(arq)
            with self.assertRaises(FileNotFoundError):
                planilha_arquivo.PastaArquivo(Path(tmp) / "nada.xlsx")


if __name__ == "__main__":
    unittest.main()
