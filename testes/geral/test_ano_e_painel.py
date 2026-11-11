"""
O que vale para todas as abas, sem navegador:

    o ano do SIGEF (automacoes/geral.py): padrão, escolha, troca na hora
    o relatório geral (automacoes/painel.py): todas as automações juntas
    a porta da janela (janela/modulo_geral.py)

    python -m unittest discover -s testes/geral -t .
"""
import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="geral_dados_"))

from automacoes import geral, painel  # noqa: E402
import automacoes.ne.etapa as ne_etapa  # noqa: E402
import automacoes.ne.lote as ne_lote  # noqa: E402
import automacoes.sigef_sei.etapa_listar_baixar as listar_baixar  # noqa: E402
import automacoes.sigef_sei.preparar_navegador as navegador  # noqa: E402

ATUAL = date.today().year


class ComConfigTemporario(unittest.TestCase):
    """Cada teste com o seu config.json, numa pasta temporária."""

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="geral_")
        self.addCleanup(shutil.rmtree, self.pasta, True)
        for nome, valor in (("PASTA_DADOS", self.pasta), ("CAMINHO_CONFIG", os.path.join(self.pasta, "config.json"))):
            p = mock.patch.object(geral, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(geral._aplicar, geral.ano_atual())  # os outros testes voltam ao padrão


class TestAnoDoSigef(ComConfigTemporario):
    def test_padrao_e_o_ano_atual(self):
        self.assertEqual(geral.ano_sigef(), ATUAL)
        self.assertEqual(geral.url_sigef("FIN/X.aspx"), f"http://sigef.sefin.ro.gov.br/SIGEF{ATUAL}/FIN/X.aspx")

    def test_escolha_fica_guardada_e_volta_ao_padrao(self):
        geral.definir_ano_sigef(ATUAL - 1)
        self.assertEqual(geral.ano_sigef(), ATUAL - 1)
        self.assertEqual(geral.ler_config()["ano_sigef"], ATUAL - 1)
        geral.definir_ano_sigef(ATUAL)  # escolher o atual apaga a escolha
        self.assertNotIn("ano_sigef", geral.ler_config())
        self.assertEqual(geral.ano_sigef(), ATUAL)

    def test_nao_apaga_o_resto_do_config(self):
        geral.gravar_config(minutos_manual_por_ob=25)
        geral.definir_ano_sigef(ATUAL - 1)
        self.assertEqual(geral.ler_config()["minutos_manual_por_ob"], 25)

    def test_ano_invalido(self):
        for ruim in (1999, ATUAL + 5, "abc", None):
            with self.assertRaises(ValueError):
                geral.definir_ano_sigef(ruim)
        self.assertEqual(geral.ano_sigef(), ATUAL)

    def test_config_estragado_usa_o_ano_atual(self):
        with open(geral.CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            f.write('{"ano_sigef": "lixo"')
        self.assertEqual(geral.ano_sigef(), ATUAL)
        geral.gravar_config(ano_sigef=1900)
        self.assertEqual(geral.ano_sigef(), ATUAL)

    def test_troca_vale_na_hora_em_todos_os_enderecos(self):
        geral.definir_ano_sigef(ATUAL - 1)
        antigo = f"SIGEF{ATUAL - 1}/"
        enderecos = [
            navegador.URL_SIGEF_LISTAR_OB, listar_baixar.URL_SIGEF_LISTAR_OB,  # a cópia importada pelo nome também
            listar_baixar.URL_SIGEF_LISTAR_NL, listar_baixar.URL_SIGEF_IMPRIMIR_OB_CONFERENCIA,
            listar_baixar.URL_SIGEF_DETALHAR_PP, listar_baixar.URL_SIGEF_DETALHAR_OB, ne_etapa.URL_SIGEF_NE,
        ]
        for url in enderecos:
            self.assertIn(antigo, url)
        self.assertEqual((ne_etapa.ANO_SIGEF, ne_lote.ANO_SIGEF), (str(ATUAL - 1), str(ATUAL - 1)))
        # A NE confere o número com o ano escolhido.
        self.assertEqual(ne_etapa.normalizar_ne(f"{ATUAL - 1}NE000123"), "000123")
        self.assertIsNone(ne_etapa.normalizar_ne(f"{ATUAL}NE000123"))
        self.assertIn(f"tela do SIGEF é de {ATUAL - 1}", ne_lote.ler_texto_ne(f"0029.001947/2026-67 {ATUAL}NE000123")[0].erro)
        # O portal de login não tem ano e não muda.
        self.assertEqual(navegador.URL_SIGEF_PORTAL, "http://sigef.sefin.ro.gov.br/SIGEF/SIGEFPortal.html")


def _csv(caminho, cabecalho, linhas):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        saida = csv.writer(f, delimiter=";")
        saida.writerow(cabecalho)
        saida.writerows(linhas)


COLS = ["Início", "Processo", "OB", "Situação", "Total (s)"]
COLS_NE = ["Início", "Processo", "NE", "Situação", "Total (s)"]
MINUTOS = {"OB": 20, "NE": 15, "DARE": 10}


class TestPainel(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="painel_")
        self.addCleanup(shutil.rmtree, self.base, True)
        eu = os.path.join(self.base, "Users", "pedro", "Documents")
        metricas = os.path.join(eu, "Automacao SIGEF-SEI", "metricas")
        _csv(os.path.join(metricas, "metricas.csv"), COLS, [
            ["05/10/2026 10:00:00", "P1", "2026OB1", "Erro", "60"],         # a mesma OB: falhou...
            ["05/10/2026 10:05:00", "P1", "2026OB1", "Concluído", "120"],   # ...e depois foi
            ["03/11/2026 09:00:00", "P2", "2026OB2", "Concluído", "100"],
            ["03/12/2026 09:00:00", "P3", "2026OB3", "Concluído", "100"],   # fora do período
        ])
        _csv(os.path.join(metricas, "metricas_ate_2026-01-01.csv"), COLS, [
            ["01/10/2026 08:00:00", "P0", "2026OB0", "Concluído", "50"],    # arquivo de versão antiga também conta
        ])
        _csv(os.path.join(metricas, "metricas_ne.csv"), COLS_NE, [
            ["06/10/2026 10:00:00", "P1", "000001", "Concluído", "90"],
        ])
        _csv(os.path.join(eu, "DARE Automação", "dados", "desempenho.csv"), ["data_hora", "status", "total_s"], [
            ["07/10/2026 10:00:00", "SUCESSO", "30,5"],
            ["07/10/2026 10:01:00", "ERRO", "10"],
        ])
        maria = os.path.join(self.base, "Users", "maria", "Documents")
        _csv(os.path.join(maria, "Automacao SIGEF-SEI", "metricas", "metricas_ne.csv"), COLS_NE, [
            ["10/11/2026 10:00:00", "P9", "000009", "Concluído", "60"],
        ])
        self.fontes = [painel.fonte_da_pasta(eu), painel.fonte_da_pasta(maria)]

    def resumo(self, fontes=None):
        return painel.resumir(date(2026, 10, 1), date(2026, 11, 30), MINUTOS, fontes or self.fontes)

    def test_acha_as_pastas_e_a_pessoa(self):
        eu, maria = self.fontes
        self.assertEqual((eu.pessoa, maria.pessoa), ("pedro", "maria"))
        self.assertTrue(eu.pasta_sigef.endswith("Automacao SIGEF-SEI") and eu.pasta_dare.endswith("DARE Automação"))
        self.assertEqual(maria.pasta_dare, "")
        self.assertEqual(painel.pessoa_do_caminho(r"C:\Users\joao\Documents\Automacao SIGEF-SEI"), "joao")
        self.assertEqual(painel.pessoa_do_caminho(r"\\servidor\equipe\ana\Automacao SIGEF-SEI"), "ana")

    def test_totais(self):
        g = self.resumo().geral
        self.assertEqual(g.concluidos, {"OB": 3, "NE": 2, "DARE": 1, "PAG": 0, "CAD": 0})
        self.assertEqual(g.tempo, {"OB": 330.0, "NE": 150.0, "DARE": 40.5, "PAG": 0.0, "CAD": 0.0})
        # concluídos x minutos à mão - tempo de todas as rodadas (as que falharam também)
        self.assertEqual(g.economia, {"OB": 3 * 1200 - 330, "NE": 2 * 900 - 150, "DARE": 600 - 40.5, "PAG": 0.0, "CAD": 0.0})

    def test_por_mes(self):
        meses = self.resumo().por_mes
        self.assertEqual(list(meses), ["2026-10", "2026-11"])
        self.assertEqual(meses["2026-10"].concluidos, {"OB": 2, "NE": 1, "DARE": 1, "PAG": 0, "CAD": 0})
        self.assertEqual(meses["2026-11"].concluidos, {"OB": 1, "NE": 1, "DARE": 0, "PAG": 0, "CAD": 0})

    def test_mes_sem_nada_aparece_zerado(self):
        meses = painel.resumir(date(2026, 9, 1), date(2026, 11, 30), MINUTOS, self.fontes).por_mes
        self.assertEqual(meses["2026-09"].total_concluidos, 0)

    def test_por_pessoa(self):
        pessoas = self.resumo().por_pessoa
        self.assertEqual(list(pessoas), ["pedro", "maria"])  # quem mais economizou primeiro
        self.assertEqual(pessoas["maria"].concluidos, {"OB": 0, "NE": 1, "DARE": 0, "PAG": 0, "CAD": 0})
        self.assertEqual(pessoas["pedro"].concluidos, {"OB": 3, "NE": 1, "DARE": 1, "PAG": 0, "CAD": 0})

    def test_mesma_pasta_duas_vezes_nao_conta_em_dobro(self):
        self.assertEqual(self.resumo(self.fontes + [self.fontes[0]]).geral.total_concluidos, 6)

    def test_datas_trocadas(self):
        r = painel.resumir(date(2026, 11, 30), date(2026, 10, 1), MINUTOS, self.fontes)
        self.assertEqual((r.de, r.ate, r.geral.total_concluidos), (date(2026, 10, 1), date(2026, 11, 30), 6))

    def test_minutos_invalidos(self):
        with self.assertRaises(ValueError):
            painel.resumir(date(2026, 10, 1), date(2026, 11, 30), {"OB": 0}, self.fontes)

    def test_pagina(self):
        destino = os.path.join(self.base, "painel.html")
        painel.gerar(date(2026, 10, 1), date(2026, 11, 30), MINUTOS, self.fontes, destino)
        html = open(destino, encoding="utf-8").read()
        for trecho in ("Relatório geral das automações", "Por automação", "Por mês", "Por pessoa", "out/2026", "nov/2026",
                       "maria", "pedro", "Nota de Empenho", "Gerar pagamento", "Cadastro de Credores", "Pular para o conteúdo"):
            self.assertIn(trecho, html)
        self.assertNotIn("Não consegui montar o detalhe", html)

    def test_sem_dados(self):
        vazio = painel.Fonte("ninguem", os.path.join(self.base, "nada"), "")
        self.assertEqual(painel.resumir(date(2026, 1, 1), date(2026, 1, 31), MINUTOS, [vazio]).geral.total_concluidos, 0)
        painel.gerar(date(2026, 1, 1), date(2026, 1, 31), MINUTOS, [vazio], os.path.join(self.base, "v.html"))


class TestGerarPagamentoECadastro(unittest.TestCase):
    """As duas automações com estimativa própria de tempo à mão."""

    def setUp(self):
        import json

        self.base = tempfile.mkdtemp(prefix="painel_pag_")
        self.addCleanup(shutil.rmtree, self.base, True)
        eu = os.path.join(self.base, "Users", "pedro", "Documents")
        pasta = os.path.join(eu, "Anexar Documentos", "relatorios")
        os.makedirs(pasta)
        etapas = [{"chave": "CE", "duracao_s": 30, "humano_s": 5}, {"chave": "SEI", "duracao_s": 20, "humano_s": 0}]
        registros = [  # o mesmo processo: parou e foi retomado; o terceiro é de fora do período
            {"id": "a", "inicio": "2026-10-05T09:00:00-04:00", "situacao": "erro", "processo": "P1", "duracao_s": 50,
             "novos": {"ce": 1}, "etapas": etapas[:1]},
            {"id": "b", "inicio": "2026-10-05T10:00:00-04:00", "situacao": "concluido", "processo": "P1", "duracao_s": 70,
             "novos": {"nl": 2}, "etapas": etapas},
            {"id": "c", "inicio": "2026-12-01T10:00:00", "situacao": "concluido", "processo": "P2", "duracao_s": 70},
        ]
        with open(os.path.join(pasta, "execucoes.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r) for r in registros) + "\nlinha cortada {")
        self.fonte = painel.fonte_da_pasta(eu)
        self.estimativas = {"CE": 3.0, "NL": 4.0, "PP": 3.0, "OB": 4.0, "CONFERENCIA": 2.0, "ANEXAR": 5.0}

    def test_gerar_pagamento(self):
        self.assertTrue(self.fonte.pasta_anexar.endswith("Anexar Documentos"))
        from automacoes.anexar.aplicativo import metricas

        with mock.patch.object(metricas, "ler_estimativas", return_value=self.estimativas):
            r = painel.resumir(date(2026, 10, 1), date(2026, 11, 30), MINUTOS, [self.fonte])
            # Um item só (o processo retomado), concluído; à mão = 1 CE x 3 + 2 NL x 4 + anexar 5 min.
            self.assertEqual((r.geral.itens["PAG"], r.geral.concluidos["PAG"], r.geral.tempo["PAG"]), (1, 1, 120.0))
            self.assertEqual(r.geral.economia["PAG"], (3 + 8 + 5) * 60 - 120)
            html = painel.gerar(date(2026, 10, 1), date(2026, 11, 30), MINUTOS, [self.fonte],
                                os.path.join(self.base, "r.html"))
        texto = open(html, encoding="utf-8").read()
        self.assertIn("Tempo de cada etapa", texto)
        self.assertNotIn("Não consegui montar o detalhe", texto)

    def test_cadastro(self):
        from automacoes.cadastro import estatisticas as est

        sessoes = [{"tipo": "sessao", "id": "s1", "inicio": "2026-10-07T10:00:00", "usuario": "ana", "itens": [
            {"status": "OK", "caminho": "novo", "segundos": 40, "espera": 2},
            {"status": "JA", "caminho": "existente", "segundos": 10},
            {"status": "ERRO", "caminho": "validacao", "segundos": 5, "motivo": "Banco inválido"},
        ]}]
        fonte = painel.Fonte("pedro", cadastro=True)
        with mock.patch.object(est, "carregar", return_value=(sessoes, [])), \
                mock.patch.object(est, "ler_ajustes", return_value={"estimativa": {"novo": 300.0, "existente": 180.0}}):
            r = painel.resumir(date(2026, 10, 1), date(2026, 10, 31), MINUTOS, [fonte, fonte])  # duas vezes: não dobra
            html = open(painel.gerar(date(2026, 10, 1), date(2026, 10, 31), MINUTOS, [fonte],
                                     os.path.join(self.base, "c.html")), encoding="utf-8").read()
        self.assertEqual((r.geral.itens["CAD"], r.geral.concluidos["CAD"]), (3, 1))
        self.assertEqual(r.geral.tempo["CAD"], 50.0)  # o recusado antes do SIGEF não conta tempo
        self.assertEqual(r.geral.economia["CAD"], 300 - 50)
        self.assertEqual(list(r.por_pessoa), ["ana"])
        self.assertIn("Banco inválido", html)


class TestPortaDaJanela(ComConfigTemporario):
    def setUp(self):
        super().setUp()
        from janela import modulo_geral, modulos_janela

        self.M, self.trava = modulo_geral, modulos_janela.USO_DO_CHROME

    def test_ano(self):
        r = self.M.chamar("ano")
        self.assertEqual((r["ano"], r["atual"]), (ATUAL, ATUAL))
        self.assertIn(ATUAL + 1, r["anos"])
        r = self.M.chamar("definir_ano", {"ano": ATUAL - 1})
        self.assertEqual((r["ok"], r["ano"]), (True, ATUAL - 1))
        self.assertFalse(self.M.chamar("definir_ano", {"ano": 1990})["ok"])

    def test_nao_troca_o_ano_com_automacao_rodando(self):
        self.assertTrue(self.trava.acquire(blocking=False))
        try:
            r = self.M.chamar("definir_ano", {"ano": ATUAL - 1})
        finally:
            self.trava.release()
        self.assertFalse(r["ok"])
        self.assertIn("rodando", r["erro"])
        self.assertEqual(geral.ano_sigef(), ATUAL)

    def test_painel_pastas_e_gerar(self):
        colega = os.path.join(self.pasta, "Users", "ana", "Documents")
        _csv(os.path.join(colega, "Automacao SIGEF-SEI", "metricas", "metricas.csv"), COLS,
             [[f"02/01/{ATUAL} 10:00:00", "P1", "OB1", "Concluído", "60"]])
        self.assertTrue(self.M._incluir(colega)["ok"])
        self.assertFalse(self.M._incluir(os.path.join(self.pasta, "vazia"))["ok"])
        self.assertEqual([p["pessoa"] for p in self.M.chamar("painel_opcoes")["pastas"]], ["ana"])
        with mock.patch.object(self.M.os, "startfile", create=True) as abrir, \
                mock.patch.object(painel, "fontes_padrao", return_value=[]), \
                mock.patch.object(painel, "PASTA_DADOS", self.pasta):
            r = self.M.chamar("painel_gerar", {"de": f"{ATUAL}-01-01", "ate": f"{ATUAL}-12-31",
                                               "minutos": {"OB": "25", "NE": 15, "DARE": 10}})
        self.assertTrue(r["ok"], r)
        abrir.assert_called_once()
        self.assertIn("ana", open(r["caminho"], encoding="utf-8").read())
        self.assertEqual(self.M.chamar("painel_opcoes")["minutos"]["OB"], 25.0)  # lembra os minutos
        self.assertEqual(self.M.chamar("painel_remover_pasta", {"caminho": colega})["pastas"], [])

    def test_painel_recusa_dados_errados(self):
        self.assertFalse(self.M.chamar("painel_gerar", {"de": "x", "ate": "y"})["ok"])
        self.assertFalse(self.M.chamar("painel_gerar", {"de": "2026-01-01", "ate": "2026-02-01",
                                                        "minutos": {"OB": -1}})["ok"])


if __name__ == "__main__":
    unittest.main()
