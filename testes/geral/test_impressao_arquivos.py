"""Retomada do SEI: só pular documento "salvo" sem aviso se os arquivos ainda são os mesmos."""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_impressao_"))

from automacoes.geral import decidir_pulo, impressao_dos_arquivos  # noqa: E402


class Impressao(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.a = os.path.join(pasta.name, "a.jpg")
        self.b = os.path.join(pasta.name, "b.jpg")
        for caminho, conteudo in ((self.a, b"aaaa"), (self.b, b"bbbb")):
            with open(caminho, "wb") as arquivo:
                arquivo.write(conteudo)

    def test_mesmos_arquivos_mesma_impressao(self):
        self.assertEqual(impressao_dos_arquivos([self.a, self.b]), impressao_dos_arquivos([self.a, self.b]))

    def test_um_byte_trocado_muda(self):
        antes = impressao_dos_arquivos([self.a, self.b])
        with open(self.b, "wb") as arquivo:
            arquivo.write(b"bbbc")
        self.assertNotEqual(impressao_dos_arquivos([self.a, self.b]), antes)

    def test_ordem_diferente_muda(self):
        self.assertNotEqual(impressao_dos_arquivos([self.a, self.b]), impressao_dos_arquivos([self.b, self.a]))

    def test_arquivo_a_mais_muda(self):
        self.assertNotEqual(impressao_dos_arquivos([self.a]), impressao_dos_arquivos([self.a, self.b]))

    def test_arquivo_ausente_nao_levanta_e_muda(self):
        ausente = self.b + ".nao_existe"
        self.assertNotEqual(impressao_dos_arquivos([self.a, ausente]), impressao_dos_arquivos([self.a, self.b]))


class DecidirPulo(unittest.TestCase):
    def test_sem_salvo_nao_pula(self):
        for estado in ({}, {"estado": "criado"}, {"estado": "criando", "impressao": "x"}):
            self.assertEqual(decidir_pulo(estado, "x", "CE 1"), (False, None))

    def test_salvo_de_registro_antigo_sem_impressao_pula_sem_aviso(self):
        self.assertEqual(decidir_pulo({"estado": "salvo"}, "x", "CE 1"), (True, None))

    def test_salvo_com_a_mesma_impressao_pula_sem_aviso(self):
        self.assertEqual(decidir_pulo({"estado": "salvo", "impressao": "x"}, "x", "CE 1"), (True, None))

    def test_salvo_com_arquivos_diferentes_pula_e_avisa(self):
        pular, aviso = decidir_pulo({"estado": "salvo", "impressao": "x"}, "y", "CE 1")
        self.assertTrue(pular)  # não cria duplicata sem decisão humana
        self.assertIn("CE 1", aviso)
        self.assertIn("os arquivos mudaram", aviso)


if __name__ == "__main__":
    unittest.main()
