"""Coleta e revisão dos lotes (editar, remover, adicionar, iniciar, cancelar)."""

import io
import unittest
from contextlib import redirect_stdout
from datetime import date
from unittest import mock

from automacoes.dare import menu
from automacoes.dare.modelos import DadosDare

CNPJ = "11.222.333/0001-81"


def lote(processo: str, cpf: str = "529.982.247-25", valor: str = "100,00") -> DadosDare:
    return DadosDare(processo, CNPJ, cpf, CNPJ, "102026", date(2026, 11, 10), valor)


class Teclado:
    """Substitui input() por uma sequência de respostas e guarda as perguntas feitas."""

    def __init__(self, respostas):
        self.respostas = iter(respostas)
        self.perguntas = []

    def __call__(self, prompt=""):
        self.perguntas.append(prompt)
        return next(self.respostas)


class TestRevisao(unittest.TestCase):
    def rodar(self, lotes, respostas):
        teclado = Teclado(respostas)
        with mock.patch("builtins.input", teclado), redirect_stdout(io.StringIO()):
            resultado = menu.revisar_lotes(lotes)
        return resultado, teclado

    def test_iniciar_exige_comando_explicito(self):
        lotes = [lote("0001.000001/2026-01")]
        ok, teclado = self.rodar(lotes, ["", "x", "i"])  # Enter e lixo não iniciam
        self.assertTrue(ok)
        self.assertEqual(len(teclado.perguntas), 3)

    def test_cancelar(self):
        ok, _ = self.rodar([lote("0001.000001/2026-01")], ["c"])
        self.assertFalse(ok)

    def test_editar_so_o_que_errou(self):
        lotes = [lote("0001.000001/2026-01"), lote("0002.000002/2026-02")]
        # E 2 -> 7 perguntas (Enter mantém), troca só o valor -> iniciar
        ok, _ = self.rodar(lotes, ["e 2", "", "", "", "", "", "", "7.243", "i"])
        self.assertTrue(ok)
        self.assertEqual(lotes[1].valor, "7.243,00")
        self.assertEqual(lotes[1].processo, "0002.000002/2026-02")  # o resto ficou igual
        self.assertEqual(lotes[0].valor, "100,00")  # o outro lote não mudou

    def test_editar_sem_numero_pergunta_qual(self):
        lotes = [lote("0001.000001/2026-01"), lote("0002.000002/2026-02")]
        self.rodar(lotes, ["e", "1", "0009.000009/2026-09", "", "", "", "", "", "", "i"])
        self.assertEqual(lotes[0].processo, "0009.000009/2026-09")

    def test_edicao_com_dado_invalido_pergunta_de_novo(self):
        lotes = [lote("0001.000001/2026-01")]
        # CPF inválido primeiro, depois um válido
        self.rodar(lotes, ["e1", "", "", "12345678901", "111.444.777-35", "", "", "", "", "i"])
        self.assertEqual(lotes[0].cpf, "111.444.777-35")

    def test_remover_pede_confirmacao(self):
        lotes = [lote("0001.000001/2026-01"), lote("0002.000002/2026-02")]
        self.rodar(lotes, ["r 1", "n", "i"])  # recusou: continua com 2
        self.assertEqual(len(lotes), 2)
        self.rodar(lotes, ["r 1", "s", "i"])
        self.assertEqual([d.processo for d in lotes], ["0002.000002/2026-02"])

    def test_nao_remove_o_unico_lote(self):
        lotes = [lote("0001.000001/2026-01")]
        self.rodar(lotes, ["r 1", "i"])
        self.assertEqual(len(lotes), 1)

    def test_numero_de_lote_invalido(self):
        lotes = [lote("0001.000001/2026-01"), lote("0002.000002/2026-02")]
        self.rodar(lotes, ["e 9", "r 0", "i"])
        self.assertEqual(len(lotes), 2)

    def test_adicionar_lote_repete_dados_do_ultimo(self):
        lotes = [lote("0001.000001/2026-01", valor="7.273,07")]
        # processo e CPF novos; o resto Enter (repete o lote anterior)
        self.rodar(lotes, ["a", "0003.000003/2026-03", "", "111.444.777-35", "", "", "", "", "i"])
        self.assertEqual(len(lotes), 2)
        self.assertEqual(lotes[1].valor, "7.273,07")
        self.assertEqual(lotes[1].vencimento, date(2026, 11, 10))
        self.assertEqual(lotes[1].cpf, "111.444.777-35")


class TestColeta(unittest.TestCase):
    def test_coleta_varios_lotes_repetindo_dados_comuns(self):
        respostas = [
            # lote 1: todos os campos
            "0029.084645/2022-92", CNPJ, "529.982.247-25", CNPJ, "102026", "10/11/2026", "7.273,07",
            "s",
            # lote 2: processo e CPF novos; o resto Enter. Começa com um CPF inválido.
            "0029.084645/2022-53", "", "61463033453", "111.444.777-35", "", "", "", "7.243",
            "n",
        ]
        with mock.patch("builtins.input", Teclado(respostas)), redirect_stdout(io.StringIO()):
            lotes = menu.coletar_lotes(None)
        self.assertEqual(len(lotes), 2)
        self.assertEqual(lotes[0].valor, "7.273,07")
        self.assertEqual(lotes[1].cnpj, CNPJ)
        self.assertEqual(lotes[1].cpf, "111.444.777-35")
        self.assertEqual(lotes[1].vencimento, date(2026, 11, 10))  # repetiu o vencimento
        self.assertEqual(lotes[1].valor, "7.243,00")


if __name__ == "__main__":
    unittest.main()
