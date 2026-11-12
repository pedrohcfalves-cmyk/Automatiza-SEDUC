"""gravar_json (automacoes/geral.py): temporário + os.replace, nunca deixa o JSON pela metade."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_atomica_"))

from automacoes import geral  # noqa: E402


class GravacaoAtomica(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = os.path.join(self.pasta.name, "dados.json")

    def test_grava_e_le_o_mesmo_dado(self):
        geral.gravar_json(self.caminho, {"ob": "2026OB000001", "açúcar": [1, 2]})
        with open(self.caminho, encoding="utf-8") as arquivo:
            self.assertEqual(json.load(arquivo), {"ob": "2026OB000001", "açúcar": [1, 2]})

    def test_falha_no_meio_mantem_o_arquivo_antigo(self):
        geral.gravar_json(self.caminho, {"antigo": True})
        with mock.patch("automacoes.geral.json.dump", side_effect=RuntimeError("queda")):
            with self.assertRaises(RuntimeError):
                geral.gravar_json(self.caminho, {"novo": True})
        with open(self.caminho, encoding="utf-8") as arquivo:
            self.assertEqual(json.load(arquivo), {"antigo": True})

    def test_nao_sobra_tmp_depois_do_sucesso(self):
        geral.gravar_json(self.caminho, {"a": 1})
        self.assertEqual(os.listdir(self.pasta.name), ["dados.json"])


if __name__ == "__main__":
    unittest.main()
