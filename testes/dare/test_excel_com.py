"""excel_com testado com um Excel/COM simulado (o Excel de verdade só existe no Windows)."""

import sys
import types
import unittest
from datetime import datetime
from unittest import mock

from automacoes.dare import excel_com, planilha
from automacoes.dare.planilha import Mapeamento


# ---- Excel de mentirinha ------------------------------------------------------------------

class Celula:
    def __init__(self, ws, linha, coluna):
        self.ws, self.Row, self.Column = ws, linha, coluna

    @property
    def Value(self):
        return self.ws.valor(self.Row, self.Column)

    Value2 = Value

    def End(self, direcao):
        assert direcao == excel_com.XL_UP
        for n in range(min(self.Row, len(self.ws.dados)), 0, -1):  # atalho do simulador
            if self.ws.valor(n, self.Column) not in (None, ""):
                return Celula(self.ws, n, self.Column)
        return Celula(self.ws, 1, self.Column)


class Linha:
    def __init__(self, ws, n):
        self.ws, self.n = ws, n

    @property
    def Hidden(self):
        return self.n in self.ws.ocultas


class Linhas:
    Count = 1048576

    def __init__(self, ws):
        self.ws = ws

    def __call__(self, n):
        return Linha(self.ws, n)


class Area:
    def __init__(self, inicio, qtd):
        self.Row = inicio
        self.Rows = types.SimpleNamespace(Count=qtd)


class Intervalo:
    def __init__(self, ws, a, b):
        self.ws, self.a, self.b = ws, a, b

    def _bloco(self):
        return [[self.ws.valor(r, c) for c in range(self.a.Column, self.b.Column + 1)]
                for r in range(self.a.Row, self.b.Row + 1)]

    @property
    def Value(self):
        bloco = self._bloco()
        if len(bloco) == 1 and len(bloco[0]) == 1:
            return bloco[0][0]
        return tuple(tuple(l) for l in bloco)

    Value2 = Value

    def SpecialCells(self, tipo):
        assert tipo == excel_com.XL_CELULAS_VISIVEIS
        l1, l2 = self.a.n, self.b.n
        areas, inicio = [], None
        for n in range(l1, l2 + 2):
            visivel = n <= l2 and n not in self.ws.ocultas
            if visivel and inicio is None:
                inicio = n
            if not visivel and inicio is not None:
                areas.append(Area(inicio, n - inicio))
                inicio = None
        if not areas:
            raise RuntimeError("Nenhuma célula foi encontrada")
        return types.SimpleNamespace(Areas=areas)


class Aba:
    def __init__(self, nome, dados, ocultas=()):
        self.Name, self.dados, self.ocultas = nome, dados, set(ocultas)
        self.Rows = Linhas(self)

    def valor(self, r, c):
        if r - 1 < len(self.dados) and c - 1 < len(self.dados[r - 1]):
            return self.dados[r - 1][c - 1]
        return None

    def Cells(self, r, c):
        return Celula(self, r, c)

    def Range(self, a, b):
        return Intervalo(self, a, b)


class Abas:
    def __init__(self, abas):
        self.abas = abas

    def __iter__(self):
        return iter(self.abas)

    def __call__(self, nome):
        for a in self.abas:
            if a.Name == nome:
                return a
        raise RuntimeError("Subscrito fora do intervalo")


class Pasta:
    def __init__(self, nome, caminho, abas, visivel=True):
        self.Name, self.FullName = nome, caminho
        self.Worksheets = Abas(abas)
        self.Windows = types.SimpleNamespace(Count=1 if visivel else 0)
        self.fechada = False

    def Close(self, salvar):
        assert salvar is False  # nunca salva a planilha do usuário
        self.fechada = True


class App:
    def __init__(self, pasta=None):
        self.pasta, self.saiu = pasta, False
        self.Workbooks = types.SimpleNamespace(Open=self._abrir)

    def _abrir(self, caminho, **kw):
        assert kw.get("ReadOnly") is True  # sempre somente leitura
        return self.pasta

    def Quit(self):
        self.saiu = True


class Moniker:
    def __init__(self, nome, obj):
        self.nome, self.obj = nome, obj

    def GetDisplayName(self, ctx, outro):
        return self.nome


class ROT:
    def __init__(self, monikers):
        self.monikers = monikers

    def EnumRunning(self):
        return list(self.monikers)

    def GetObject(self, m):
        return types.SimpleNamespace(QueryInterface=lambda iid: m.obj)


def instalar_com(monikers=(), app=None):
    pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: None, GetRunningObjectTable=lambda: ROT(monikers),
        CreateBindCtx=lambda n: None, IID_IDispatch=object(),
    )
    cliente = types.SimpleNamespace(
        Dispatch=lambda x: x, DispatchEx=lambda nome: app,
        GetActiveObject=lambda nome: app if app else (_ for _ in ()).throw(RuntimeError("sem Excel")),
    )
    win32com = types.SimpleNamespace(client=cliente)
    return mock.patch.dict(sys.modules, {
        "pythoncom": pythoncom, "win32com": win32com, "win32com.client": cliente})


DADOS = [["Processo", "CPF", "Valor"], ["0012.123456/2026-12", "52998224725", 10.5], [], ["x", None, None]]


class TestLeitura(unittest.TestCase):
    def tabela(self, ocultas=()):
        pasta = Pasta("p.xlsx", "C:\\p.xlsx", [Aba("Dados", DADOS, ocultas)])
        return excel_com.TabelaExcel(pasta, "Dados")

    def test_ler_bloco_e_celula_unica(self):
        t = self.tabela()
        self.assertEqual(t.ler(1, 1, 2, 2), [["Processo", "CPF"], ["0012.123456/2026-12", "52998224725"]])
        self.assertEqual(t.ler(2, 3, 2, 3), [[10.5]])  # uma célula só: o COM devolve valor solto
        self.assertEqual(t.ler(1, 1, 1, 3), [["Processo", "CPF", "Valor"]])

    def test_erro_de_celula_vira_vazio_e_data_vira_datetime(self):
        pasta = Pasta("p.xlsx", "x", [Aba("A", [[-2146826246, datetime(2026, 1, 2, 3, 4)]])])
        t = excel_com.TabelaExcel(pasta, "A")
        self.assertEqual(t.ler(1, 1, 1, 2), [[None, datetime(2026, 1, 2, 3, 4)]])

    def test_ultima_linha(self):
        t = self.tabela()
        self.assertEqual(t.ultima_linha([1]), 4)
        self.assertEqual(t.ultima_linha([2]), 2)
        self.assertEqual(t.ultima_linha([5]), 0)

    def test_linhas_ocultas(self):
        self.assertEqual(self.tabela({2, 3}).linhas_ocultas(1, 4), {2, 3})
        self.assertEqual(self.tabela().linhas_ocultas(1, 4), set())
        self.assertEqual(self.tabela({1, 2}).linhas_ocultas(1, 2), {1, 2})  # nenhuma visível -> erro -> plano B

    def test_aba_inexistente(self):
        pasta = Pasta("p.xlsx", "x", [Aba("A", [])])
        with self.assertRaises(ValueError):
            excel_com.TabelaExcel(pasta, "Z")

    def test_leitura_completa_pela_tabela_excel(self):
        dados = [["Nº Processo", "CPF", "CNPJ", "Recolhedor", "Ref", "Vencimento", "Valor"],
                 ["0012.123456/2026-12", 52998224725.0, "11222333000181", "11.222.333/0001-81",
                  102026.0, datetime(2026, 11, 10), 7273.07],
                 [None] * 7]
        t = excel_com.TabelaExcel(Pasta("p.xlsx", "x", [Aba("A", dados)]), "A")
        cab = planilha.ler_cabecalhos(t, 1)
        m = Mapeamento(planilha.sugerir_mapeamento(cab), 1)
        self.assertEqual(m.faltando(), [])
        r = planilha.ler_lotes(t, m, 2, planilha.ultima_linha_com_dados(t, m))
        self.assertEqual(r.problemas, [])
        self.assertEqual(r.lotes[0].valor, "7.273,07")
        self.assertEqual(r.lotes[0].origem, "linha 2")


class TestAbertas(unittest.TestCase):
    def test_lista_pela_rot_ignora_ocultas_e_nao_planilhas(self):
        a = Pasta("a.xlsx", "C:\\a.xlsx", [Aba("Dados", []), Aba("Outra", [])])
        oculta = Pasta("PERSONAL.XLSB", "C:\\PERSONAL.XLSB", [Aba("X", [])], visivel=False)
        monikers = [Moniker("C:\\a.xlsx", a), Moniker("C:\\a.xlsx", a), Moniker("C:\\x.docx", object()),
                    Moniker("C:\\PERSONAL.XLSB", oculta), Moniker("!{GUID}", object())]
        with instalar_com(monikers):
            abertas = excel_com.listar_abertas()
        self.assertEqual([p.nome for p in abertas], ["a.xlsx"])
        self.assertEqual(abertas[0].abas(), ["Dados", "Outra"])
        self.assertFalse(abertas[0].aberta_por_nos)

    def test_sem_excel_aberto(self):
        with instalar_com([]):
            self.assertEqual(excel_com.listar_abertas(), [])

    def test_pywin32_ausente(self):
        with mock.patch.dict(sys.modules, {"pythoncom": None}):
            with self.assertRaises(excel_com.ExcelIndisponivel):
                excel_com.listar_abertas()


class TestAbrirPorCaminho(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.tmp.name) / "dados.xlsx"
        self.arquivo.write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_arquivo_inexistente_e_extensao(self):
        with instalar_com():
            with self.assertRaises(FileNotFoundError):
                excel_com.abrir_por_caminho(self.arquivo.with_name("nao.xlsx"))
            txt = self.arquivo.with_suffix(".txt")
            txt.write_text("x")
            with self.assertRaises(excel_com.ExcelIndisponivel):
                excel_com.abrir_por_caminho(txt)

    def test_usa_a_ja_aberta(self):
        pasta = Pasta("dados.xlsx", str(self.arquivo.resolve()), [Aba("A", [])])
        with instalar_com([Moniker(pasta.FullName, pasta)]):
            p = excel_com.abrir_por_caminho(self.arquivo)
        self.assertFalse(p.aberta_por_nos)
        p.fechar()
        self.assertFalse(pasta.fechada)  # nunca fecha o que é do usuário

    def test_abre_somente_leitura_e_fecha_sem_salvar(self):
        pasta = Pasta("dados.xlsx", str(self.arquivo.resolve()), [Aba("A", [])])
        app = App(pasta)
        with instalar_com([], app):
            p = excel_com.abrir_por_caminho(f'"{self.arquivo}"')  # aspas coladas do Explorer
            self.assertTrue(p.aberta_por_nos)
            p.fechar()
        self.assertTrue(pasta.fechada)
        self.assertTrue(app.saiu)

    def test_falha_ao_abrir_encerra_o_excel(self):
        app = App()
        app.Workbooks.Open = mock.Mock(side_effect=RuntimeError("senha"))
        with instalar_com([], app):
            with self.assertRaises(excel_com.ExcelIndisponivel):
                excel_com.abrir_por_caminho(self.arquivo)
        self.assertTrue(app.saiu)


class TestModelo(unittest.TestCase):
    def test_cabecalhos_do_modelo_sao_reconhecidos(self):
        cab = dict(enumerate(excel_com.MODELO_CABECALHOS, 1))
        self.assertEqual(Mapeamento(planilha.sugerir_mapeamento(cab)).faltando(), [])
        self.assertEqual(len(planilha.sugerir_mapeamento(cab)), 7)


if __name__ == "__main__":
    unittest.main()
