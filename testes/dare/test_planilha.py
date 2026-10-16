"""Modo planilha: reconhecimento de colunas, conversão de células e leitura por intervalo."""

import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from automacoes.dare import config, planilha, utils
from automacoes.dare.planilha import Mapeamento, Origem, TabelaMemoria

CPF = "52998224725"
CNPJ = "11222333000181"


COLUNAS_PADRAO = dict(processo=1, cnpj=2, cpf=3, cnpj_recolhedor=4, mes_ano_referencia=5, vencimento=6, valor=7)


def linha_ok(proc="0012.123456/2026-12"):
    return [proc, CNPJ, CPF, CNPJ, "102026", date(2026, 11, 10), 7273.07]


class TestColunas(unittest.TestCase):
    def test_letras(self):
        self.assertEqual(planilha.letra_para_numero("A"), 1)
        self.assertEqual(planilha.letra_para_numero("aa"), 27)
        self.assertEqual(planilha.numero_para_letra(26), "Z")
        self.assertEqual(planilha.numero_para_letra(27), "AA")
        for n in (1, 26, 27, 52, 702, 703, 16384):
            self.assertEqual(planilha.letra_para_numero(planilha.numero_para_letra(n)), n)


class TestReconhecimento(unittest.TestCase):
    def test_cabecalhos_variados(self):
        cab = {1: "Nº do Processo", 2: "CNPJ Órgão", 3: "CPF Servidor", 4: "CNPJ Recolhedor",
               5: "Referência", 6: "Data Vencimento", 7: "Valor Principal (R$)"}
        s = planilha.sugerir_mapeamento(cab)
        self.assertEqual({c: o.coluna for c, o in s.items()}, {
            "processo": 1, "cnpj": 2, "cpf": 3, "cnpj_recolhedor": 4,
            "mes_ano_referencia": 5, "vencimento": 6, "valor": 7})

    def test_cnpj_recolhedor_nao_vira_cnpj(self):
        s = planilha.sugerir_mapeamento({1: "CNPJ do Recolhedor", 2: "CPF"})
        self.assertNotIn("cnpj", s)
        self.assertEqual(s["cnpj_recolhedor"].coluna, 1)

    def test_colunas_embaralhadas_e_extras(self):
        cab = {1: "Nome", 2: "Valor", 3: "Obs", 5: "CPF", 9: "Processo"}
        s = planilha.sugerir_mapeamento(cab)
        self.assertEqual((s["valor"].coluna, s["cpf"].coluna, s["processo"].coluna), (2, 5, 9))

    def test_detecta_linha_do_cabecalho_na_linha_3(self):
        dados = [["Relatório de DAREs"], [], ["Processo", "CNPJ", "CPF", "Recolhedor", "Ref", "Venc", "Valor"],
                 linha_ok()]
        self.assertEqual(planilha.detectar_linha_cabecalho(TabelaMemoria(dados)), 3)

    def test_sem_cabecalho_devolve_zero(self):
        self.assertEqual(planilha.detectar_linha_cabecalho(TabelaMemoria([linha_ok(), linha_ok()])), 0)

    def test_interpretar_origem(self):
        cab = {1: "Processo", 2: "Valor", 3: "Valor total"}
        io = planilha.interpretar_origem
        self.assertEqual(io("c", cab), Origem(coluna=3))
        self.assertEqual(io("AB", cab), Origem(coluna=28))
        self.assertEqual(io("4", cab), Origem(coluna=4))
        self.assertEqual(io("=100,00", cab), Origem(fixo="100,00"))
        self.assertTrue(io("-", cab).vazia)
        self.assertEqual(io("processo", cab), Origem(coluna=1))
        with self.assertRaises(ValueError):
            io("valor total xyz", cab)
        with self.assertRaises(ValueError):
            io("=", cab)


class TestConversao(unittest.TestCase):
    def test_documento_recupera_zeros(self):
        self.assertEqual(planilha.para_documento(11222333000181.0, 14, "CNPJ", utils.validar_cnpj), CNPJ)
        # CPF que começa com zero: o Excel guarda como número e "come" o zero
        cpf_zero = next(f"{n:011d}" for n in range(1, 10**6) if utils.validar_cpf(f"{n:011d}"))
        self.assertEqual(planilha.para_documento(float(int(cpf_zero)), 11, "CPF", utils.validar_cpf), cpf_zero)

    def test_documento_formatado_e_invalido(self):
        self.assertEqual(planilha.para_documento("529.982.247-25", 11, "CPF", utils.validar_cpf), CPF)
        with self.assertRaises(ValueError):
            planilha.para_documento("529.982.247-26", 11, "CPF", utils.validar_cpf)
        with self.assertRaises(ValueError):
            planilha.para_documento("1234567890123456", 14, "CNPJ", utils.validar_cnpj)
        with self.assertRaises(ValueError):
            planilha.para_documento(None, 11, "CPF", utils.validar_cpf)

    def test_mes_ano(self):
        f = planilha.para_mes_ano
        self.assertEqual(f("102026"), "102026")
        self.assertEqual(f(102026), "102026")
        self.assertEqual(f(102026.0), "102026")
        self.assertEqual(f(92026), "092026")
        self.assertEqual(f("10/2026"), "102026")
        self.assertEqual(f("2026-10"), "102026")
        self.assertEqual(f(datetime(2026, 10, 1)), "102026")
        self.assertEqual(f("out/2026"), "102026")
        with self.assertRaises(ValueError):
            f("132026")
        with self.assertRaises(ValueError):
            f(None)

    def test_data(self):
        f = planilha.para_data
        self.assertEqual(f(datetime(2026, 11, 10, 0, 0)), date(2026, 11, 10))
        self.assertEqual(f("10/11/2026"), date(2026, 11, 10))
        self.assertEqual(f(46336), date(2026, 11, 10))  # número serial do Excel
        self.assertEqual(f("2026-11-10"), date(2026, 11, 10))
        self.assertIsNone(f(None))
        self.assertIsNone(f("  "))
        with self.assertRaises(ValueError):
            f("amanhã")
        with self.assertRaises(ValueError):
            f(7)

    def test_valor(self):
        f = planilha.para_valor
        self.assertEqual(f(None, 7273.07), "7.273,07")
        self.assertEqual(f("R$ 7.273,07", None), "7.273,07")
        self.assertEqual(f(None, None), "100,00")
        self.assertEqual(f(None, Decimal("100.5")), "100,50")
        self.assertEqual(f("x", 5), "5,00")
        with self.assertRaises(ValueError):
            f("abc", None)

    def test_texto_celula(self):
        self.assertEqual(planilha.texto_celula(61463035268.0), "61463035268")
        self.assertEqual(planilha.texto_celula(datetime(2026, 1, 2)), "02/01/2026")
        self.assertEqual(planilha.texto_celula(None), "")


class TestLerLotes(unittest.TestCase):
    def mapeamento(self, cab=1, **troca):
        cols = dict(COLUNAS_PADRAO, **troca)
        return Mapeamento({c: Origem(coluna=n) for c, n in cols.items()}, cab)

    def test_layout_simples(self):
        t = TabelaMemoria([["h"] * 7, linha_ok(), linha_ok("0012.123456/2026-99")])
        r = planilha.ler_lotes(t, self.mapeamento(), 2, 3)
        self.assertEqual(len(r.lotes), 2)
        self.assertEqual(r.lotes[0].origem, "linha 2")
        self.assertEqual(r.lotes[1].processo, "0012.123456/2026-99")
        d = r.lotes[0]
        self.assertEqual((d.cnpj, d.cpf, d.mes_ano_referencia, d.valor, d.vencimento),
                         (CNPJ, CPF, "102026", "7.273,07", date(2026, 11, 10)))

    def test_colunas_embaralhadas_com_lixo_entre_elas(self):
        # valor, lixo, processo, ... qualquer ordem e posição
        linha = [7273.07, "x", "0012.123456/2026-12", None, CPF, "102026", CNPJ, "y", CNPJ, "10/11/2026"]
        t = TabelaMemoria([linha])
        m = self.mapeamento(0, valor=1, processo=3, cpf=5, mes_ano_referencia=6, cnpj=7,
                            cnpj_recolhedor=9, vencimento=10)
        r = planilha.ler_lotes(t, m, 1, 1)
        self.assertEqual(r.problemas, [])
        self.assertEqual(r.lotes[0].valor, "7.273,07")
        self.assertEqual(r.lotes[0].vencimento, date(2026, 11, 10))

    def test_intervalo_respeita_inicio_e_fim(self):
        dados = [linha_ok(f"0012.12345{i}/2026-12") for i in range(1, 7)]
        r = planilha.ler_lotes(TabelaMemoria(dados), self.mapeamento(0), 3, 4)
        self.assertEqual([d.origem for d in r.lotes], ["linha 3", "linha 4"])

    def test_vazias_ocultas_e_problemas(self):
        ruim = linha_ok()
        ruim[2] = "111.111.111-11"  # CPF inválido
        dados = [linha_ok(), [], [None] * 7, ruim, linha_ok("0012.123456/2026-55"), linha_ok("0012.123456/2026-66")]
        t = TabelaMemoria(dados, ocultas={6})
        r = planilha.ler_lotes(t, self.mapeamento(0), 1, 6)
        self.assertEqual([d.origem for d in r.lotes], ["linha 1", "linha 5"])
        self.assertEqual(r.vazias, 2)
        self.assertEqual(r.ocultas, 1)
        self.assertEqual(len(r.problemas), 1)
        self.assertEqual(r.problemas[0].linha, 4)
        self.assertIn("CPF", r.problemas[0].mensagem)

    def test_padroes_de_vencimento_e_valor(self):
        linha = linha_ok()
        linha[5] = None
        linha[6] = None
        r = planilha.ler_lotes(TabelaMemoria([linha]), self.mapeamento(0), 1, 1)
        self.assertEqual(r.lotes[0].valor, config.VALOR_PADRAO)
        self.assertEqual(r.lotes[0].vencimento, utils.vencimento_padrao())

    def test_vencimento_serial_e_valor_fixo(self):
        linha = linha_ok()
        linha[5] = datetime(2026, 11, 10)
        m = self.mapeamento(0)
        m.campos["valor"] = Origem(fixo="250,00")
        r = planilha.ler_lotes(TabelaMemoria([linha]), m, 1, 1)
        self.assertEqual(r.lotes[0].vencimento, date(2026, 11, 10))
        self.assertEqual(r.lotes[0].valor, "250,00")

    def test_cpf_numerico_sem_zero_a_esquerda(self):
        cpf_zero = next(f"{n:011d}" for n in range(1, 10**6) if utils.validar_cpf(f"{n:011d}"))
        linha = linha_ok()
        linha[2] = float(int(cpf_zero))
        r = planilha.ler_lotes(TabelaMemoria([linha]), self.mapeamento(0), 1, 1)
        self.assertEqual(r.lotes[0].cpf, cpf_zero)

    def test_campo_obrigatorio_sem_origem(self):
        m = self.mapeamento(0)
        del m.campos["cpf"]
        with self.assertRaises(ValueError):
            planilha.ler_lotes(TabelaMemoria([linha_ok()]), m, 1, 1)

    def test_intervalo_invalido(self):
        with self.assertRaises(ValueError):
            planilha.ler_lotes(TabelaMemoria([linha_ok()]), self.mapeamento(0), 3, 2)

    def test_ultima_linha_ignora_colunas_nao_mapeadas(self):
        dados = [linha_ok(), linha_ok(), [None] * 7 + ["lixo"] * 3]
        t = TabelaMemoria(dados)
        self.assertEqual(planilha.ultima_linha_com_dados(t, self.mapeamento(0)), 2)


class TestMapeamentoSalvo(unittest.TestCase):
    def test_ida_e_volta(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(config, "PASTA_DADOS", Path(tmp)), \
                mock.patch.object(config, "ARQ_MAPEAMENTOS", Path(tmp) / "m.json"):
            m = Mapeamento({"processo": Origem(coluna=3), "valor": Origem(fixo="9,00")}, 2)
            chave = planilha.chave_mapeamento("Folha.xlsx", "Abril")
            self.assertIsNone(planilha.carregar_mapeamento(chave))
            planilha.salvar_mapeamento(chave, m)
            lido = planilha.carregar_mapeamento(planilha.chave_mapeamento("FOLHA.xlsx", "abril"))
            self.assertEqual(lido.linha_cabecalho, 2)
            self.assertEqual(lido.origem("processo"), Origem(coluna=3))
            self.assertEqual(lido.origem("valor"), Origem(fixo="9,00"))
            (Path(tmp) / "m.json").write_text("{quebrado", encoding="utf-8")
            self.assertIsNone(planilha.carregar_mapeamento(chave))


if __name__ == "__main__":
    unittest.main()
