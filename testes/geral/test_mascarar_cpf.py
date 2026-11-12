"""mascarar_cpf (automacoes/geral.py): o CPF inteiro não vai para registro nem log."""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_cpf_"))

from automacoes.geral import mascarar_cpf  # noqa: E402


class MascararCpf(unittest.TestCase):
    def test_com_e_sem_pontuacao(self):
        self.assertEqual(mascarar_cpf("123.456.789-09"), "***.456.789-**")
        self.assertEqual(mascarar_cpf("12345678909"), "***.456.789-**")

    def test_o_que_nao_e_cpf_some_inteiro(self):
        for entrada in ("x", "", None, "11.222.333/0001-81"):
            self.assertEqual(mascarar_cpf(entrada), "***", entrada)


if __name__ == "__main__":
    unittest.main()
