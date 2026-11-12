"""processo_na_arvore (automacoes/geral.py): o SEI abriu mesmo o processo pedido?"""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_arvore_"))

from automacoes.geral import processo_na_arvore  # noqa: E402

PROCESSO = "0029.123456/2026-12"


class ProcessoNaArvore(unittest.TestCase):
    def test_mesmo_numero_com_pontuacao(self):
        self.assertTrue(processo_na_arvore(f"Processo {PROCESSO}\nOfício 12", PROCESSO))

    def test_pedido_sem_pontuacao(self):
        self.assertTrue(processo_na_arvore(f"Processo {PROCESSO}", "0029123456202612"))

    def test_outro_processo_na_tela(self):
        self.assertFalse(processo_na_arvore("Processo 0029.999999/2026-12", PROCESSO))

    def test_numero_no_meio_de_outros_numeros(self):
        self.assertTrue(processo_na_arvore(f"Despacho 77 (2026) {PROCESSO} Nota 2026NE000123", PROCESSO))

    def test_pedido_vazio_ou_none_nao_aprova(self):
        self.assertFalse(processo_na_arvore(f"Processo {PROCESSO}", ""))
        self.assertFalse(processo_na_arvore(f"Processo {PROCESSO}", None))

    def test_pedido_curto_demais_nao_aprova(self):
        self.assertFalse(processo_na_arvore("Ofício 12 de 2026", "12"))

    def test_arvore_vazia_ou_none(self):
        self.assertFalse(processo_na_arvore("", PROCESSO))
        self.assertFalse(processo_na_arvore(None, PROCESSO))


class _Arvore:
    def __init__(self, texto):
        self.texto = texto

    def locator(self, _seletor):
        return self

    def inner_text(self):
        return self.texto


class _Clicavel:
    def __getattr__(self, _nome):
        return lambda *a, **k: self


class _AbaSei(_Clicavel):
    """Aba do SEI de mentira: a pesquisa "funciona", e a árvore mostra o texto dado."""
    url = "https://sei.exemplo/controlador.php?acao=procedimento_trabalhar"

    def __init__(self, texto_arvore):
        self._arvore = _Arvore(texto_arvore)

    def frame(self, name=None):
        return self._arvore

    def wait_for_timeout(self, _ms):
        pass


class AbrirProcessoConfere(unittest.TestCase):
    """Os dois fluxos param ANTES de anexar se a árvore é de outro processo."""

    def test_sigef_sei_para_se_a_arvore_e_de_outro_processo(self):
        from unittest import mock
        from automacoes.sigef_sei import etapa_listar_baixar as elb
        with mock.patch.object(elb, "procurar_em_frames", return_value=(None, _Clicavel())):
            with self.assertRaisesRegex(RuntimeError, "não abriu o processo"):
                elb.abrir_processo_sei(_AbaSei("Processo 0029.999999/2026-12"), PROCESSO, timeout_ms=300)

    def test_sigef_sei_segue_com_o_processo_certo(self):
        from unittest import mock
        from automacoes.sigef_sei import etapa_listar_baixar as elb
        aba = _AbaSei("Processo 0029.999999/2026-12")  # o atalho "já aberto" não serve: é outro processo
        aba._arvore = _Arvore(f"Processo {PROCESSO}")
        with mock.patch.object(elb, "procurar_em_frames", return_value=(None, _Clicavel())):
            self.assertIs(elb.abrir_processo_sei(aba, PROCESSO, timeout_ms=300), aba)

    def test_anexar_sei2_para_se_a_arvore_e_de_outro_processo(self):
        from unittest import mock
        from automacoes.anexar.automacao import etapa_sei2
        with mock.patch.object(etapa_sei2, "procurar_em_frames", return_value=(None, _Clicavel())), \
                mock.patch.object(etapa_sei2, "_aguardar_rede"):
            with self.assertRaisesRegex(RuntimeError, "não abriu o processo"):
                etapa_sei2.abrir_processo_sei(_AbaSei("Processo 0029.999999/2026-12"), PROCESSO, timeout_ms=300)

    def test_anexar_para_se_a_arvore_e_de_outro_processo(self):
        from automacoes.anexar.automacao import etapa_sei1
        with self.assertRaisesRegex(RuntimeError, "não abriu o processo"):
            etapa_sei1.abrir_processo_sei(_AbaSei("Processo 0029.999999/2026-12"), PROCESSO, timeout_ms=400)

    def test_anexar_segue_com_o_processo_certo(self):
        from automacoes.anexar.automacao import etapa_sei1
        etapa_sei1.abrir_processo_sei(_AbaSei(f"Processo {PROCESSO}"), PROCESSO, timeout_ms=400)


if __name__ == "__main__":
    unittest.main()
