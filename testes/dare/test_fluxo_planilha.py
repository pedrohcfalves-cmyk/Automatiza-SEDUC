"""Fluxo interativo do modo planilha, com teclado simulado e planilhas em memória."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from automacoes.dare import terminal as dare_automacao
from automacoes.dare import config, excel_com, fluxo_planilha, menu
from automacoes.dare.modelos import DadosDare
from automacoes.dare.planilha import TabelaMemoria
from testes.dare.test_excel_com import Aba, Pasta
from testes.dare.test_revisao import Teclado

CPF, CNPJ = "52998224725", "11222333000181"
CAB = ["Nº Processo", "CNPJ Órgão", "CPF Servidor", "CNPJ Recolhedor", "Referência", "Vencimento", "Valor"]


def linha(proc, cpf=CPF):
    return [proc, CNPJ, cpf, CNPJ, "102026", date(2026, 11, 10), 100.0]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        for nome, valor in (("PASTA_DADOS", tmp), ("ARQ_MAPEAMENTOS", tmp / "map.json"),
                            ("ARQ_LOTE", tmp / "lote.json"), ("PASTA_MODELOS", tmp / "modelos")):
            p = mock.patch.object(config, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def rodar(self, funcao, respostas, *args):
        teclado = Teclado(respostas)
        saida = io.StringIO()
        with mock.patch("builtins.input", teclado), redirect_stdout(saida):
            resultado = funcao(*args)
        self.texto = saida.getvalue()
        return resultado, teclado


class TestConfigurarELer(Base):
    def tabela(self, extra=()):
        dados = [["Relatório"], [], CAB, linha("0012.123456/2026-01"), linha("0012.123456/2026-02"),
                 [], linha("0012.123456/2026-03"), *extra]
        return TabelaMemoria(dados, "folha.xlsx", "Abril")

    def test_deteccao_automatica_e_ultima_linha_por_padrao(self):
        lotes, t = self.rodar(fluxo_planilha.configurar_e_ler, ["", "", ""], self.tabela())
        self.assertEqual([d.origem for d in lotes], ["linha 4", "linha 5", "linha 7"])
        self.assertIn("linha 3", self.texto)  # cabeçalho achado sozinho na linha 3

    def test_linhas_inicial_e_final_escolhidas(self):
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, ["", "5", "5"], self.tabela())
        self.assertEqual([d.origem for d in lotes], ["linha 5"])

    def test_final_alem_da_ultima_e_validacoes(self):
        # inicial 99 (> última) -> refaz; inicial 4 + final 3 (< inicial) -> refaz; inicial 4 + final 500 (vira 7)
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler,
                              ["", "99", "4", "3", "4", "500"], self.tabela())
        self.assertEqual(len(lotes), 3)

    def test_mapeamento_salvo_e_reaproveitado(self):
        self.rodar(fluxo_planilha.configurar_e_ler, ["", "", ""], self.tabela())
        self.assertTrue(config.ARQ_MAPEAMENTOS.exists())
        lotes, teclado = self.rodar(fluxo_planilha.configurar_e_ler, ["", "", ""], self.tabela())
        self.assertIn("salvo da última vez", self.texto)
        self.assertEqual(len(lotes), 3)

    def test_cabecalhos_nao_reconhecidos_pedem_colunas(self):
        dados = [["a", "b", "c", "d", "e", "f", "g"], ["0012.123456/2026-01", CNPJ, CPF, CNPJ, "102026", "", ""]]
        t = TabelaMemoria(dados, "estranha.xlsx", "P")
        # linha do cabeçalho 1; processo A, cnpj B, cpf C, recolhedor D, ref E, venc F, valor =250,00
        respostas = ["1", "A", "B", "C", "D", "E", "-", "=250,00", "", "", ""]
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, respostas, t)
        self.assertEqual(lotes[0].valor, "250,00")
        self.assertEqual(lotes[0].cpf, CPF)

    def test_editor_rejeita_obrigatorio_vazio_e_coluna_inexistente(self):
        dados = [["a"] * 7, linha("0012.123456/2026-01")]
        t = TabelaMemoria(dados, "x.xlsx", "P")
        respostas = ["1", "-", "A", "zz zz", "B", "C", "D", "E", "-", "-", "", "", ""]
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, respostas, t)
        self.assertEqual(len(lotes), 1)
        self.assertIn("obrigatório", self.texto)
        self.assertIn("Não achei a coluna", self.texto)

    def test_recusar_mapeamento_reabre_editor(self):
        respostas = ["n", "3", "A", "B", "C", "D", "E", "F", "G", "", "", ""]
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, respostas, self.tabela())
        self.assertEqual(len(lotes), 3)

    def test_linhas_com_problema_ficam_de_fora(self):
        t = self.tabela(extra=[linha("0012.123456/2026-04", cpf="111.111.111-11")])
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, ["", "", "", ""], t)
        self.assertEqual(len(lotes), 3)
        self.assertIn("Linha 8", self.texto)
        self.assertIn("CPF", self.texto)

    def test_recusar_continuar_com_problemas_cancela(self):
        t = self.tabela(extra=[linha("0012.123456/2026-04", cpf="111.111.111-11")])
        lotes, _ = self.rodar(fluxo_planilha.configurar_e_ler, ["", "", "", "n"], t)
        self.assertIsNone(lotes)

    def test_sem_nenhuma_linha_valida(self):
        t = TabelaMemoria([CAB, linha("0012.123456/2026-04", cpf="111.111.111-11")], "x.xlsx", "P")
        with mock.patch("builtins.input", Teclado(["", "", "", ""])), redirect_stdout(io.StringIO()):
            self.assertIsNone(fluxo_planilha.configurar_e_ler(t))

    def test_planilha_sem_dados(self):
        t = TabelaMemoria([CAB], "x.xlsx", "P")
        with mock.patch("builtins.input", Teclado(["", ""])), redirect_stdout(io.StringIO()):
            self.assertIsNone(fluxo_planilha.configurar_e_ler(t))


class TestObterLotes(Base):
    def pasta_aberta(self, abas):
        com = Pasta("folha.xlsx", "C:\\folha.xlsx", abas)
        return excel_com.PastaAberta("folha.xlsx", "C:\\folha.xlsx", com)

    def test_escolhe_planilha_aberta_e_aba_por_numero(self):
        abas = [Aba("Capa", [["nada"]]), Aba("Dados", [CAB, linha("0012.123456/2026-01")])]
        pasta = self.pasta_aberta(abas)
        with mock.patch.object(excel_com, "listar_abertas", return_value=[pasta]):
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, ["1", "2", "", "", ""])
        self.assertEqual([d.origem for d in lotes], ["linha 2"])

    def test_aba_por_nome(self):
        abas = [Aba("Capa", []), Aba("Dados", [CAB, linha("0012.123456/2026-01")])]
        with mock.patch.object(excel_com, "listar_abertas", return_value=[self.pasta_aberta(abas)]):
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, ["1", "xx", "dados", "", "", ""])
        self.assertEqual(len(lotes), 1)

    def test_caminho_digitado_e_fechamento(self):
        com = Pasta("f.xlsx", "C:\\f.xlsx", [Aba("U", [CAB, linha("0012.123456/2026-01")])])
        nossa = excel_com.PastaAberta("f.xlsx", "C:\\f.xlsx", com, aplicativo=mock.Mock(), aberta_por_nos=True)
        with mock.patch.object(excel_com, "listar_abertas", return_value=[]), \
                mock.patch.object(excel_com, "abrir_por_caminho", return_value=nossa) as abrir:
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, ["c", "C:\\f.xlsx", "", "", ""])
        abrir.assert_called_once_with("C:\\f.xlsx")
        self.assertEqual(len(lotes), 1)
        self.assertTrue(com.fechada)  # a que abrimos é fechada sem salvar

    def test_caminho_inexistente_volta_a_lista_e_zero_sai(self):
        with mock.patch.object(excel_com, "listar_abertas", return_value=[]), \
                mock.patch.object(excel_com, "abrir_por_caminho", side_effect=FileNotFoundError("nao existe")):
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, ["c", "C:\\x.xlsx", "", "0"])
        self.assertIsNone(lotes)
        self.assertIn("nao existe", self.texto)

    def test_sem_pywin32(self):
        with mock.patch.object(excel_com, "listar_abertas", side_effect=excel_com.ExcelIndisponivel("sem pywin32")):
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, [""])
        self.assertIsNone(lotes)
        self.assertIn("sem pywin32", self.texto)

    def test_erro_de_com_na_leitura_nao_derruba(self):
        pasta = self.pasta_aberta([Aba("Dados", [CAB])])
        with mock.patch.object(excel_com, "listar_abertas", return_value=[pasta]), \
                mock.patch.object(fluxo_planilha, "configurar_e_ler", side_effect=RuntimeError("COM caiu")):
            lotes, _ = self.rodar(fluxo_planilha.obter_lotes, ["1", ""])
        self.assertIsNone(lotes)
        self.assertIn("COM caiu", self.texto)

    def test_criar_modelo_pelo_menu(self):
        with mock.patch.object(excel_com, "listar_abertas", return_value=[]), \
                mock.patch.object(excel_com, "criar_modelo") as criar, \
                mock.patch.object(fluxo_planilha, "_abrir_arquivo_no_windows"):
            self.rodar(fluxo_planilha.obter_lotes, ["m", "", "0"])
        criar.assert_called_once()
        self.assertEqual(criar.call_args.args[0].name, "modelo_dare.xlsx")


class TestMain(Base):
    def lote(self):
        return DadosDare("0012.123456/2026-01", CNPJ, CPF, CNPJ, "102026", date(2026, 11, 10), "100,00", "linha 4")

    def test_rotulo(self):
        d = self.lote()
        self.assertEqual(dare_automacao._rotulo(1, 3, d), "Lote 1/3 (linha 4)")
        self.assertEqual(dare_automacao._rotulo(1, 1, d), "Lote 1/1 (linha 4)")
        d.origem = ""
        self.assertEqual(dare_automacao._rotulo(1, 1, d), "")
        self.assertEqual(dare_automacao._rotulo(2, 3, d), "Lote 2/3")

    def test_opcao_planilha_leva_ao_fluxo_de_conferencia(self):
        lotes = [self.lote()]
        with mock.patch.object(dare_automacao.armazenamento, "carregar_lote", return_value=None), \
                mock.patch.object(dare_automacao.fluxo_planilha, "obter_lotes", return_value=lotes), \
                mock.patch.object(dare_automacao, "_conferir_e_rodar") as rodar:
            dare_automacao._opcao_planilha()
        rodar.assert_called_once_with(lotes)

    def test_opcao_planilha_cancelada_nao_roda_nada(self):
        with mock.patch.object(dare_automacao.armazenamento, "carregar_lote", return_value=None), \
                mock.patch.object(dare_automacao.fluxo_planilha, "obter_lotes", return_value=None), \
                mock.patch.object(dare_automacao, "_conferir_e_rodar") as rodar:
            dare_automacao._opcao_planilha()
        rodar.assert_not_called()

    def test_pendentes_podem_ser_retomados_no_modo_planilha(self):
        lotes = [self.lote()]
        with mock.patch.object(dare_automacao.armazenamento, "carregar_lote", return_value=lotes), \
                mock.patch("builtins.input", Teclado([""])), redirect_stdout(io.StringIO()), \
                mock.patch.object(dare_automacao.fluxo_planilha, "obter_lotes") as obter, \
                mock.patch.object(dare_automacao, "_conferir_e_rodar") as rodar:
            dare_automacao._opcao_planilha()
        obter.assert_not_called()
        rodar.assert_called_once_with(lotes)

    def test_origem_sobrevive_ao_arquivo_de_pendentes_e_a_edicao(self):
        d = self.lote()
        self.assertEqual(DadosDare.de_dict(d.para_dict()).origem, "linha 4")
        antigo = d.para_dict()
        antigo.pop("origem")  # arquivo salvo por versão anterior
        self.assertEqual(DadosDare.de_dict(antigo).origem, "")
        lotes = [d]
        # editar o lote 1 mantendo tudo (Enter em tudo) e depois iniciar
        respostas = ["e 1", "", "", "", "", "", "", "", "i"]
        with mock.patch("builtins.input", Teclado(respostas)), redirect_stdout(io.StringIO()):
            self.assertTrue(menu.revisar_lotes(lotes))
        self.assertEqual(lotes[0].origem, "linha 4")

    def test_menu_principal_tem_as_duas_modalidades(self):
        with mock.patch("builtins.input", Teclado(["2"])), redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(menu.menu_principal(True), "2")
        self.assertIn("Modo em lotes", saida.getvalue())
        self.assertIn("Modo planilha", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
