import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from automacoes.dare import utils


class TestDocumentos(unittest.TestCase):
    def test_cpf(self):
        self.assertTrue(utils.validar_cpf("529.982.247-25"))
        self.assertTrue(utils.validar_cpf("52998224725"))
        self.assertFalse(utils.validar_cpf("529.982.247-24"))
        self.assertFalse(utils.validar_cpf("111.111.111-11"))
        self.assertFalse(utils.validar_cpf("123"))

    def test_cnpj(self):
        self.assertTrue(utils.validar_cnpj("11.222.333/0001-81"))
        self.assertFalse(utils.validar_cnpj("11.222.333/0001-80"))
        self.assertFalse(utils.validar_cnpj("00.000.000/0000-00"))

    def test_formatacao_e_mascara(self):
        self.assertEqual(utils.formatar_cpf("52998224725"), "529.982.247-25")
        self.assertEqual(utils.formatar_cnpj("11222333000181"), "11.222.333/0001-81")
        self.assertEqual(utils.mascarar_cpf("529.982.247-25"), "***.982.247-**")


class TestDatas(unittest.TestCase):
    def test_vencimento_padrao_dia_util(self):
        self.assertEqual(utils.vencimento_padrao(date(2026, 10, 13)), date(2026, 11, 13))  # sexta
        self.assertEqual(utils.vencimento_padrao(date(2026, 1, 31)), date(2026, 3, 2))  # 28/02 é sábado
        self.assertEqual(utils.vencimento_padrao(date(2026, 12, 15)), date(2027, 1, 15))  # virada de ano

    def test_ler_vencimento(self):
        self.assertEqual(utils.ler_vencimento("25/12/2026"), date(2026, 12, 25))
        with self.assertRaises(ValueError):
            utils.ler_vencimento("2026-12-25")

    def test_mes_ano(self):
        self.assertEqual(utils.validar_mes_ano("10/2026"), "102026")
        self.assertEqual(utils.validar_mes_ano("102026"), "102026")
        for ruim in ("132026", "10", "abc"):
            with self.assertRaises(ValueError):
                utils.validar_mes_ano(ruim)
        self.assertEqual(utils.formatar_mes_ano("102026"), "10/2026")


class TestValores(unittest.TestCase):
    def test_para_digitos(self):
        casos = {"": "10000", "100,00": "10000", "100": "10000", "1.500,5": "150050", "R$ 99,99": "9999"}
        for entrada, esperado in casos.items():
            self.assertEqual(utils.valor_para_digitos(entrada), esperado, entrada)

    def test_ponto_de_milhar_sem_virgula(self):
        # "7.243" no padrão brasileiro é sete mil duzentos e quarenta e três
        self.assertEqual(utils.valor_para_digitos("7.243"), "724300")
        self.assertEqual(utils.valor_para_digitos("1.234.567"), "123456700")
        self.assertEqual(utils.valor_para_digitos("7.273,07"), "727307")
        self.assertEqual(utils.valor_para_digitos("100.5"), "10050")  # ponto decimal
        self.assertEqual(utils.formatar_valor("7.243"), "7.243,00")

    def test_invalidos(self):
        for ruim in ("abc", "0", "-5"):
            with self.assertRaises(ValueError):
                utils.valor_para_digitos(ruim)

    def test_formatar(self):
        self.assertEqual(utils.formatar_valor("100"), "100,00")
        self.assertEqual(utils.formatar_valor("1500,5"), "1.500,50")


class TestArquivos(unittest.TestCase):
    def test_nome_seguro(self):
        self.assertEqual(utils.nome_arquivo_seguro("JOÃO da Silva/Jr"), "JOÃO_da_SilvaJr")
        self.assertEqual(utils.nome_arquivo_seguro("  "), "SEM_NOME")

    def test_sem_conflito(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "dare.pdf"
            self.assertEqual(utils.caminho_sem_conflito(base), base)
            base.write_bytes(b"x")
            self.assertEqual(utils.caminho_sem_conflito(base).name, "dare (2).pdf")


if __name__ == "__main__":
    unittest.main()
