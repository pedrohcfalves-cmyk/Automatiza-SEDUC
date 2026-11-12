"""
As duas cópias de etapa_sei2.py (sigef_sei e anexar).

As funções puras da divisão em partes só têm testes na cópia de sigef_sei
(testes/testes_divisao.py). Em vez de repetir os casos, aqui se garante que
essas funções continuam IDÊNTICAS nas duas cópias -- mexeu numa, este teste
manda mexer na outra (ou escrever os testes da cópia que divergiu).
O que já diverge (ProgressoSei do Anexar, por lote de PPs) é testado direto.
"""
import os
import sys
import tempfile
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "testes", "ferramentas"))
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_sei2_copias_"))

import comparar_funcoes  # noqa: E402
from automacoes.anexar.automacao import etapa_sei2 as anexar  # noqa: E402

PURAS = ("_em_mb", "_eh_erro_de_tamanho", "_sequencial_ob", "_dividir_em_partes", "_planejar_partes",
         "_obs_concluidas", "_tamanho_estimado_imagem", "_proximo_passo")
PROCESSO = "0029.001947/2026-67"


class FuncoesPurasIguais(unittest.TestCase):
    def test_puras_identicas_nas_duas_copias(self):
        a, b = comparar_funcoes.definicoes(comparar_funcoes.A), comparar_funcoes.definicoes(comparar_funcoes.B)
        for nome in PURAS:
            self.assertEqual(a[nome][0], b[nome][0], f"{nome} divergiu entre sigef_sei e anexar")


class ProgressoDoAnexar(unittest.TestCase):
    # diverge de sigef_sei: a chave do arquivo é "lote" (os PPs do lote), não "ob"
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.base = pasta.name

    def test_retoma_o_mesmo_lote(self):
        anexar.ProgressoSei(PROCESSO, "PP1+PP2", self.base).marcar("CE 1", "salvo", partes=1)
        de_novo = anexar.ProgressoSei(PROCESSO, "PP1+PP2", self.base)
        self.assertTrue(de_novo.retomando)
        self.assertEqual(de_novo.estado("CE 1"), {"estado": "salvo", "partes": 1})
        self.assertEqual(de_novo.estado("NL 1"), {})

    def test_outro_lote_nao_retoma(self):
        anexar.ProgressoSei(PROCESSO, "PP1+PP2", self.base).marcar("CE 1", "salvo")
        self.assertFalse(anexar.ProgressoSei(PROCESSO, "PP3", self.base).retomando)

    def test_tentativa_velha_demais_nao_retoma(self):
        progresso = anexar.ProgressoSei(PROCESSO, "PP1", self.base)
        progresso.marcar("CE 1", "salvo")
        velho = time.time() - (anexar.PRAZO_RETOMADA_HORAS + 1) * 3600
        os.utime(progresso.caminho, (velho, velho))
        self.assertFalse(anexar.ProgressoSei(PROCESSO, "PP1", self.base).retomando)

    def test_arquivo_corrompido_comeca_do_zero(self):
        progresso = anexar.ProgressoSei(PROCESSO, "PP1", self.base)
        progresso.marcar("CE 1", "salvo")
        with open(progresso.caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write('{"lote": "PP1", "docum')
        self.assertFalse(anexar.ProgressoSei(PROCESSO, "PP1", self.base).retomando)

    def test_concluir_guarda_as_obs_sem_repetir_e_apaga_o_andamento(self):
        progresso = anexar.ProgressoSei(PROCESSO, "PP1", self.base)
        progresso.marcar("CE 1", "salvo")
        progresso.concluir(["2026OB000001"])
        anexar.ProgressoSei(PROCESSO, "PP2", self.base).concluir(["000001", "2026OB000002"])
        self.assertFalse(os.path.exists(progresso.caminho))
        self.assertEqual(anexar._obs_concluidas(progresso.pasta), ["2026OB000001", "2026OB000002"])
        self.assertTrue(anexar.ob_ja_concluida(PROCESSO, "000002", self.base))
        self.assertFalse(anexar.ob_ja_concluida(PROCESSO, "000003", self.base))


if __name__ == "__main__":
    unittest.main()
