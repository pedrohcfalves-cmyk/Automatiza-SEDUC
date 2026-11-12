"""Reserva (janela/reserva.py): um trabalho do Chrome por vez, contado desde o clique."""
import os
import sys
import threading
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from janela.reserva import Reserva  # noqa: E402


class TestaReserva(unittest.TestCase):
    def test_primeira_reserva_passa_e_a_segunda_e_recusada(self):
        reserva = Reserva()
        self.assertTrue(reserva.tentar())
        self.assertTrue(reserva.ocupada)
        self.assertFalse(reserva.tentar())

    def test_liberar_permite_reservar_de_novo(self):
        reserva = Reserva()
        reserva.tentar()
        reserva.liberar()
        self.assertFalse(reserva.ocupada)
        self.assertTrue(reserva.tentar())

    def test_cinquenta_threads_disputando_so_uma_vence(self):
        reserva = Reserva()
        largada = threading.Barrier(50)
        resultados = []

        def disputar():
            largada.wait()
            resultados.append(reserva.tentar())

        threads = [threading.Thread(target=disputar) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(resultados.count(True), 1)


if __name__ == "__main__":
    unittest.main()
