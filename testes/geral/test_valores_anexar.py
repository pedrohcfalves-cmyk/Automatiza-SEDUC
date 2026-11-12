"""valores.py do Anexar: ponto sem vírgula só vale como milhar; o resto é ambíguo e vira erro."""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from automacoes.anexar.automacao.valores import normalizar, padronizar_valor  # noqa: E402


class FormatosDeSempre(unittest.TestCase):
    def test_normalizar(self):
        for texto, esperado in (("79054", 790.54), ("790,54", 790.54), ("1.234,56", 1234.56), ("R$ 1.105,50", 1105.5)):
            self.assertAlmostEqual(normalizar(texto), esperado, msg=texto)

    def test_padronizar_valor(self):
        for texto in ("1.105,50", "110550", "1105,5"):
            self.assertEqual(padronizar_valor(texto), ("110550", "1.105,50"), texto)

    def test_vazio_e_negativo_sao_erro(self):
        for texto in ("", "-5,00", "abc"):
            with self.assertRaises(ValueError, msg=texto):
                padronizar_valor(texto)


class PontoSemVirgula(unittest.TestCase):
    def test_decimal_com_ponto_e_ambiguo(self):
        # "1105.50" virava 110.550,00 (cem vezes mais) sem aviso
        for texto in ("1105.50", "100.5", "0.99", "12.5"):
            with self.assertRaisesRegex(ValueError, "vírgula", msg=texto):
                padronizar_valor(texto)

    def test_normalizar_tambem_recusa(self):
        with self.assertRaises(ValueError):
            normalizar("1105.50")

    def test_ponto_de_milhar_continua_valendo(self):
        self.assertEqual(padronizar_valor("7.243"), ("724300", "7.243,00"))
        self.assertEqual(padronizar_valor("1.234.567"), ("123456700", "1.234.567,00"))
        self.assertAlmostEqual(normalizar("7.243"), 7243.0)


if __name__ == "__main__":
    unittest.main()
