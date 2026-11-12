"""instalador/construir.py: não gera instalador de uma versão sem notas no CHANGELOG."""
import importlib.util
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("construir", os.path.join(RAIZ, "instalador", "construir.py"))
construir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(construir)  # só define as funções: o main() fica atrás do __name__


class ChangelogTemVersao(unittest.TestCase):
    def test_tem_a_secao(self):
        self.assertTrue(construir.changelog_tem_versao("# H\n\n## [3.9.0] - 2026-11-03\n\n- x\n", "3.9.0"))

    def test_nao_tem_a_secao(self):
        self.assertFalse(construir.changelog_tem_versao("## [3.8.0] - 2026-10-01\n", "3.9.0"))

    def test_nao_lancado_sozinho_nao_conta(self):
        self.assertFalse(construir.changelog_tem_versao("## [Não lançado]\n\n- mudanças da 3.9.1\n", "3.9.1"))

    def test_o_ponto_da_versao_e_ponto_mesmo(self):
        self.assertFalse(construir.changelog_tem_versao("## [3x9x0]\n", "3.9.0"))

    def test_so_vale_como_titulo_de_secao(self):
        self.assertFalse(construir.changelog_tem_versao("texto ## [3.9.0] no meio da linha\n", "3.9.0"))

    def test_o_changelog_do_projeto_tem_a_versao_do_main(self):
        with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as arquivo:
            self.assertTrue(construir.changelog_tem_versao(arquivo.read(), construir.ler_versao()))


if __name__ == "__main__":
    unittest.main()
