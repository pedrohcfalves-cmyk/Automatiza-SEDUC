"""digitar_valor_conferido (Anexar): o valor digitado no SIGEF é lido de volta; não bateu = para."""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from automacoes.anexar.automacao.valores import digitar_valor_conferido, padronizar_valor  # noqa: E402


class CampoFalso:
    """Campo de valor do SIGEF: o que se digita (só dígitos) aparece formatado ('325850' -> '3.258,50')."""

    def __init__(self, texto="", ignora_backspace=False, sempre_vazio=False):
        self.digitos = "".join(c for c in texto if c.isdigit())
        self.selecionado = False
        self.ignora_backspace, self.sempre_vazio = ignora_backspace, sempre_vazio

    def click(self):
        pass

    def press(self, tecla):
        if tecla == "Control+A":
            self.selecionado = True
        elif tecla == "Backspace" and self.selecionado and not self.ignora_backspace:
            self.digitos = ""

    def press_sequentially(self, texto, delay=0):
        self.digitos += texto
        self.selecionado = False

    def input_value(self):
        return "" if self.sempre_vazio or not self.digitos else padronizar_valor(self.digitos)[1]


class PaginaFalsa:
    def __init__(self):
        self.esperas = []

    def wait_for_timeout(self, ms):
        self.esperas.append(ms)


class DigitarValorConferido(unittest.TestCase):
    def test_campo_vazio(self):
        self.assertEqual(digitar_valor_conferido(PaginaFalsa(), CampoFalso(), "325850"), "3.258,50")

    def test_campo_ja_preenchido_e_limpo_antes(self):
        # sem limpar, "999" + "325850" viraria 9.993.258,50
        self.assertEqual(digitar_valor_conferido(PaginaFalsa(), CampoFalso("999"), "325850"), "3.258,50")

    def test_campo_que_nao_limpa_para_com_erro(self):
        campo = CampoFalso("999", ignora_backspace=True)
        with self.assertRaisesRegex(RuntimeError, "em vez de"):
            digitar_valor_conferido(PaginaFalsa(), campo, "325850")

    def test_campo_que_volta_vazio_para_com_erro(self):
        with self.assertRaises(RuntimeError):
            digitar_valor_conferido(PaginaFalsa(), CampoFalso(sempre_vazio=True), "325850")

    def test_espera_antes_de_cada_tentativa(self):
        pagina = PaginaFalsa()
        with self.assertRaises(RuntimeError):
            digitar_valor_conferido(pagina, CampoFalso(sempre_vazio=True), "325850", antes_ms=2000)
        self.assertEqual(pagina.esperas, [2000, 300] * 3)


if __name__ == "__main__":
    unittest.main()
