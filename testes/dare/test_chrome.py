"""Abertura automática do Chrome (sem abrir nenhum processo de verdade)."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import config, navegador


class TestIniciarChrome(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(config, "PERFIL_CHROME", Path(self.tmp.name) / "perfil")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(navegador.time, "sleep", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def test_ja_aberto_nao_abre_outro(self):
        with mock.patch.object(navegador, "chrome_debug_ativo", return_value=True), \
                mock.patch.object(navegador.subprocess, "Popen") as popen:
            self.assertTrue(navegador.iniciar_chrome())
            popen.assert_not_called()

    def test_abre_com_porta_perfil_e_as_duas_abas(self):
        estados = iter([False, False, False, True])  # a porta só responde na 3ª checagem
        with mock.patch.object(navegador, "chrome_debug_ativo", lambda *a: next(estados)), \
                mock.patch.object(navegador, "localizar_chrome", return_value="/x/chrome"), \
                mock.patch.object(navegador.subprocess, "Popen") as popen:
            self.assertTrue(navegador.iniciar_chrome(espera=30))
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "/x/chrome")
        self.assertIn(f"--remote-debugging-port={config.PORTA_CDP}", args)
        self.assertIn(f"--user-data-dir={config.PERFIL_CHROME}", args)
        self.assertIn("--disable-renderer-backgrounding", args)
        self.assertEqual(args[-2:], [config.URL_SEI, config.URL_DARE])

    def test_chrome_nao_instalado(self):
        with mock.patch.object(navegador, "chrome_debug_ativo", return_value=False), \
                mock.patch.object(navegador, "localizar_chrome", return_value=None), \
                mock.patch.object(navegador.subprocess, "Popen") as popen:
            self.assertFalse(navegador.iniciar_chrome())
            popen.assert_not_called()

    def test_porta_nunca_responde(self):
        with mock.patch.object(navegador, "chrome_debug_ativo", return_value=False), \
                mock.patch.object(navegador, "localizar_chrome", return_value="/x/chrome"), \
                mock.patch.object(navegador.subprocess, "Popen"):
            self.assertFalse(navegador.iniciar_chrome(espera=0.05))

    def test_localizar_por_variavel_de_ambiente(self):
        exe = Path(self.tmp.name) / "meu_chrome.exe"
        exe.write_text("x")
        with mock.patch.dict(os.environ, {"DARE_CHROME_PATH": str(exe)}):
            self.assertEqual(navegador.localizar_chrome(), str(exe))


class TestObterAba(unittest.TestCase):
    def test_espera_aba_em_branco_carregar_em_vez_de_duplicar(self):
        aba = mock.MagicMock()
        aba.url = "about:blank"
        contexto = mock.MagicMock()
        contexto.pages = [aba]
        esperas = []

        def dormir(segundos):  # a aba termina de carregar depois de duas esperas
            esperas.append(segundos)
            if len(esperas) == 2:
                aba.url = f"https://{config.HOST_SEI}/sip/login.php"

        with mock.patch.object(navegador.time, "sleep", dormir):
            achada, criada = navegador.obter_aba(contexto, config.HOST_SEI, config.URL_SEI)
        self.assertIs(achada, aba)
        self.assertFalse(criada)
        contexto.new_page.assert_not_called()

    def test_sem_a_aba_abre_uma_nova(self):
        outra = mock.MagicMock()
        outra.url = "https://exemplo.com/"
        contexto = mock.MagicMock()
        contexto.pages = [outra]
        navegador.obter_aba(contexto, config.HOST_DARE, config.URL_DARE)
        contexto.new_page.assert_called_once()


if __name__ == "__main__":
    unittest.main()
