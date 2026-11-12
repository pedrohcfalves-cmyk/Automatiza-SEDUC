"""modulos_janela.rodar / bb_executar: a trava do Chrome vem antes de mexer no estado do BB."""
import os
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_trava_"))

from janela import modulos_janela as M  # noqa: E402


class RodarETrava(unittest.TestCase):
    def setUp(self):
        self.assertTrue(M.USO_DO_CHROME.acquire(blocking=False), "outro teste deixou a trava presa")
        self.presa = True
        self.addCleanup(self._soltar)
        self.eventos = []
        self.fim = threading.Event()

    def _soltar(self):
        if self.presa:
            M.USO_DO_CHROME.release()

    def emitir(self, tipo, **dados):
        self.eventos.append(tipo)
        if tipo == "modulo_fim":
            self.fim.set()

    def test_trava_ocupada_recusa_e_nao_roda(self):
        funcao = mock.Mock()
        r = M.rodar("bb", "teste", funcao, self.emitir)
        self.assertFalse(r["ok"])
        funcao.assert_not_called()
        self.assertEqual(self.eventos, [])

    def test_ja_reservado_roda_e_solta_no_fim(self):
        funcao = mock.Mock()
        r = M.rodar("bb", "teste", funcao, self.emitir, ja_reservado=True)
        self.assertTrue(r["ok"])
        self.assertTrue(self.fim.wait(5))
        funcao.assert_called_once()
        self.presa = False  # a thread soltou
        self.assertTrue(M.USO_DO_CHROME.acquire(blocking=False))
        M.USO_DO_CHROME.release()

    def test_bb_executar_com_a_trava_ocupada_nao_mexe_no_estado(self):
        parada = threading.Event()
        parada.set()  # "Parar" pedido na execução que está rodando
        funcao = mock.Mock(__name__="automacao_falsa", sem_planilha=True)
        bb = types.SimpleNamespace(AUTOMACOES=[("Falsa", funcao)], PEDIDO_PARADA=parada, ErroDeUso=Exception)
        M._fila_bb.put("resposta da execução em andamento")
        self.addCleanup(lambda: M._fila_bb.empty() or M._fila_bb.get_nowait())
        with mock.patch.object(M, "_bb", lambda: bb), mock.patch.object(M, "bb_salvar", lambda v: mock.Mock()), \
                mock.patch.object(M, "_validar_respostas_bb", lambda *a: ""), \
                mock.patch.object(M, "_instalar_respostas_bb") as instalar:
            r = M.bb_executar({}, 0, self.emitir)
        self.assertFalse(r["ok"])
        self.assertIn("Já tem uma automação rodando", r["erro"])
        self.assertTrue(parada.is_set(), "o pedido de parada da execução em andamento foi apagado")
        self.assertFalse(M._fila_bb.empty(), "a fila de respostas da execução em andamento foi esvaziada")
        instalar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
