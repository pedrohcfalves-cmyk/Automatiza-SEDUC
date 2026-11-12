"""A reserva do "Processar": o segundo clique é recusado em vez de enfileirar a mesma automação de novo."""
import threading


class Reserva:
    """Um trabalho do Chrome por vez, contado desde o clique (não só desde que roda)."""

    def __init__(self):
        self._trava = threading.Lock()
        self._ocupada = False

    def tentar(self) -> bool:
        with self._trava:
            if self._ocupada:
                return False
            self._ocupada = True
            return True

    def liberar(self) -> None:
        with self._trava:
            self._ocupada = False

    @property
    def ocupada(self) -> bool:
        return self._ocupada


# A da fila do Trabalhador (OB, lote, NE, lote de NE): app_janela.py e janela/modulo_ne.py usam esta mesma.
RESERVA = Reserva()
OCUPADA = {"ok": False, "erro": "Já há uma automação em andamento. Espere terminar."}
