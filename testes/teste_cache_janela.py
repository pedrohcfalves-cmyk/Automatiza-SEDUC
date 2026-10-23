"""
Teste offline da limpeza do cache da janela (janela/cache_janela.py).

    python testes/teste_cache_janela.py
"""
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from janela import cache_janela  # noqa: E402


class TestaLimparCache(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="teste_cache_")
        self.default = os.path.join(self.pasta, "EBWebView", "Default")

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def _arquivo(self, *partes):
        caminho = os.path.join(self.default, *partes)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write("x")
        return caminho

    def test_apaga_o_cache_e_preserva_o_resto(self):
        velho = self._arquivo("Cache", "Cache_Data", "f_000001")
        codigo = self._arquivo("Code Cache", "js", "index")
        cookies = self._arquivo("Network", "Cookies")
        local = self._arquivo("Local Storage", "leveldb", "000003.log")

        apagadas = cache_janela.limpar(self.pasta)

        self.assertEqual(sorted(apagadas), ["Cache", "Code Cache"])
        self.assertFalse(os.path.exists(velho))
        self.assertFalse(os.path.exists(codigo))
        self.assertTrue(os.path.exists(cookies))
        self.assertTrue(os.path.exists(local))

    def test_pasta_inexistente_nao_da_erro(self):
        self.assertEqual(cache_janela.limpar(os.path.join(self.pasta, "nao_existe")), [])

    def test_sem_cache_nao_da_erro(self):
        self._arquivo("Network", "Cookies")
        self.assertEqual(cache_janela.limpar(self.pasta), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
