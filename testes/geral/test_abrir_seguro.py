"""pode_abrir (automacoes/geral.py): a janela não abre programas/scripts a pedido da página."""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_abrir_"))

from automacoes import geral  # noqa: E402


class PodeAbrir(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def _arquivo(self, nome):
        caminho = os.path.join(self.pasta.name, nome)
        open(caminho, "w").close()
        return caminho

    def test_documento_que_existe_abre(self):
        for nome in ("relatorio.txt", "planilha.xlsx", "DARE_1.pdf", "pagina.html"):
            self.assertTrue(geral.pode_abrir(self._arquivo(nome)), nome)

    def test_pasta_abre(self):
        self.assertTrue(geral.pode_abrir(self.pasta.name))

    def test_executavel_e_script_nao_abrem(self):
        for nome in ("x.exe", "x.BAT", "x.Cmd", "x.ps1", "x.js", "x.lnk", "x.msi", "x.vbs", "x.hta"):
            self.assertFalse(geral.pode_abrir(self._arquivo(nome)), nome)

    def test_caminho_que_nao_existe_nao_abre(self):
        self.assertFalse(geral.pode_abrir(os.path.join(self.pasta.name, "nao_existe.txt")))

    def test_vazio_e_none_nao_abrem(self):
        self.assertFalse(geral.pode_abrir(""))
        self.assertFalse(geral.pode_abrir(None))


if __name__ == "__main__":
    unittest.main()
