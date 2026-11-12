"""Anexar: trocar o número do processo não reaproveita CE/NL/PP/OB do processo anterior."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="teste_sessao_"))

from automacoes.anexar.automacao import modo_treino, utils  # noqa: E402

A, B = "0029.001947/2026-67", "0029.002180/2026-93"
LANCAMENTOS = [{"valor": "1.105,50", "nota_de_empenho": "2026NE000001", "nl": "2026NL000009"}]


class FuncaoPura(unittest.TestCase):
    def sessao(self):
        return {"processo": A, "escola": "EE Teste", "ce": "018705", "ob": "2026OB000001",
                "lancamentos": list(LANCAMENTOS), "avisos_download": ["x"]}

    def test_mesmo_processo_fica_intacta(self):
        self.assertEqual(utils.sessao_ao_trocar_de_processo(self.sessao(), A), self.sessao())

    def test_mesmo_processo_escrito_sem_pontuacao_fica_intacta(self):
        self.assertEqual(utils.sessao_ao_trocar_de_processo(self.sessao(), "0029001947202667"), self.sessao())

    def test_outro_processo_perde_o_que_era_do_anterior(self):
        nova = utils.sessao_ao_trocar_de_processo(self.sessao(), B)
        self.assertEqual(nova, {"processo": A, "escola": "EE Teste"})  # os dados reaproveitáveis ficam

    def test_sessao_sem_processo_fica_intacta(self):
        sessao = {"lancamentos": list(LANCAMENTOS), "ce": "018705"}
        self.assertEqual(utils.sessao_ao_trocar_de_processo(sessao, B), sessao)


class SalvarSessao(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.caminho = os.path.join(pasta.name, "sessao_atual.json")
        for modulo in (utils, modo_treino):
            for alvo, nome, valor in ((modulo, "CAMINHO_SESSAO", self.caminho), (modulo.interacao, "avisar", mock.Mock())):
                p = mock.patch.object(alvo, nome, valor)
                p.start()
                self.addCleanup(p.stop)

    def gravado(self):
        with open(self.caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)

    def test_trocar_de_processo_apaga_os_lancamentos_do_anterior(self):
        for salvar in (utils.salvar_sessao, modo_treino.salvar_sessao):
            with self.subTest(salvar.__module__):
                salvar(processo=A, ce="018705", escola="EE Teste", lancamentos=list(LANCAMENTOS))
                salvar(processo=B)
                self.assertEqual(self.gravado(), {"processo": B, "escola": "EE Teste"})

    def test_mesmo_processo_mantem_tudo(self):
        utils.salvar_sessao(processo=A, ce="018705", lancamentos=list(LANCAMENTOS))
        utils.salvar_sessao(processo=A)
        self.assertEqual(self.gravado()["lancamentos"], LANCAMENTOS)

    def test_o_que_vem_junto_com_o_processo_novo_e_gravado(self):
        utils.salvar_sessao(processo=A, lancamentos=list(LANCAMENTOS))
        utils.salvar_sessao(processo=B, lancamentos=[{"valor": "1,00"}])
        self.assertEqual(self.gravado()["lancamentos"], [{"valor": "1,00"}])


if __name__ == "__main__":
    unittest.main()
