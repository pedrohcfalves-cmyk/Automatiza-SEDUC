"""
Testes da ponte entre a janela da Central e o DARE (janela/modulo_dare.py).
Sem navegador e sem Excel: o motor é simulado e a planilha é lida do arquivo.
"""
import os
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from automacoes.dare import config, motor, navegador  # noqa: E402
from automacoes.dare.modelos import ResultadoLote  # noqa: E402
from janela import modulo_dare as M, modulos_janela  # noqa: E402

CNPJ = "04.287.520/0001-88"
CPF = "529.982.247-25"


class Base(unittest.TestCase):
    def setUp(self):
        # Todas as pastas do DARE numa pasta temporária (nunca em Documentos).
        tmp = tempfile.TemporaryDirectory(prefix="dare_ponte_")
        self.addCleanup(tmp.cleanup)
        base = self.base = Path(tmp.name)
        alvos = {
            "BASE_DADOS": base, "PASTA_DADOS": base / "dados", "PASTA_PDF": base / "pdf",
            "PASTA_PDF_PADRAO": base / "pdf", "PASTA_LOGS": base / "logs", "PASTA_MODELOS": base / "modelos",
            "ARQ_LOG": base / "logs" / "dare.log", "ARQ_ULTIMOS": base / "dados" / "u.json",
            "ARQ_HISTORICO": base / "dados" / "h.csv", "ARQ_LOTE": base / "dados" / "l.json",
            "ARQ_MAPEAMENTOS": base / "dados" / "m.json", "ARQ_PREFERENCIAS": base / "dados" / "p.json",
            "ARQ_DESEMPENHO": base / "dados" / "d.csv", "ARQ_BENCHMARKS": base / "dados" / "b.json",
        }
        for nome, valor in alvos.items():
            p = mock.patch.object(config, nome, valor)
            p.start(); self.addCleanup(p.stop)
        self.eventos = []
        M.configurar(lambda tipo, **d: self.eventos.append((tipo, d)), lambda: None)
        M._e.lotes.clear()
        M._e.executando = False
        p = mock.patch.object(navegador, "chrome_debug_ativo", lambda timeout=0.4: False)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(navegador, "localizar_chrome", lambda: None)
        p.start(); self.addCleanup(p.stop)

    def valores(self, processo="0012.123456/2026-12", cpf=CPF):
        venc = (date.today() + timedelta(days=30)).strftime("%d/%m/%Y")
        return {"processo": processo, "cpf": cpf, "cnpj": CNPJ, "recolhedor": CNPJ,
                "ref": "102026", "venc": venc, "valor": "7.273,07"}


class TestPasta(unittest.TestCase):
    def test_dados_em_documentos_e_nao_na_pasta_do_codigo(self):
        if os.environ.get("DARE_PASTA_DADOS"):
            self.skipTest("DARE_PASTA_DADOS definida")
        from automacoes.dare import config as c
        self.assertEqual(c.BASE_DADOS.name, "DARE Automação")
        self.assertNotIn(str(RAIZ), str(c.BASE_DADOS))


class TestFormulario(Base):
    def test_validacao_igual_ao_dare(self):
        self.assertEqual(M.chamar("validar", {"campo": "cpf", "texto": "52998224725"}),
                         {"ok": True, "valor": CPF})
        r = M.chamar("validar", {"campo": "cpf", "texto": "12345678900"})
        self.assertFalse(r["ok"]); self.assertIn("dígitos verificadores", r["erro"])
        r = M.chamar("validar", {"campo": "cnpj", "texto": "123"})
        self.assertEqual(r["erro"], "O CNPJ deve ter 14 dígitos (tem 3).")
        self.assertEqual(M.chamar("validar", {"campo": "venc", "texto": "10112026"})["valor"], "10/11/2026")
        self.assertEqual(M.chamar("validar", {"campo": "ref", "texto": "102026"})["valor"], "10/2026")
        self.assertFalse(M.chamar("validar", {"campo": "processo", "texto": "  "})["ok"])

    def test_salvar_editar_duplicar_remover(self):
        r = M.chamar("salvar", {"valores": self.valores()})
        self.assertTrue(r["ok"]); self.assertEqual(r["n"], 1)
        self.assertEqual(r["novo"]["campos"]["cnpj"], CNPJ)        # o próximo herda o CNPJ
        self.assertEqual(r["novo"]["campos"]["processo"], "")      # processo sempre em branco
        r = M.chamar("salvar", {"valores": {**self.valores(), "cpf": "111"}})
        self.assertFalse(r["ok"]); self.assertIn("cpf", r["erros"])
        r = M.chamar("duplicar", {"indice": 0})
        self.assertEqual(len(r["lista"]["linhas"]), 2)
        self.assertTrue(any("mesmo processo, CPF e referência" in a for a in r["lista"]["avisos"]))
        e = M.chamar("editar", {"indice": 1})
        self.assertEqual(e["titulo"], "Editando o lançamento 2")
        r = M.chamar("salvar", {"valores": {**self.valores(), "processo": "0012.999999/2026-12"}, "indice": 1})
        self.assertEqual(r["mensagem"], "Lançamento 2 atualizado.")
        self.assertIn("total R$ 14.546,14", r["lista"]["total"])
        r = M.chamar("remover", {"indices": [0]})
        self.assertEqual([l["processo"] for l in r["lista"]["linhas"]], ["0012.999999/2026-12"])
        # a lista sobrevive a fechar o programa (lote_pendente.json), como no DARE
        self.assertTrue(config.ARQ_LOTE.exists())
        M.chamar("esvaziar")
        self.assertFalse(config.ARQ_LOTE.exists())


class TestExecucao(Base):
    def test_rodada_com_motor_simulado_usa_a_trava_do_chrome(self):
        M.chamar("salvar", {"valores": self.valores()})
        M.chamar("salvar", {"valores": self.valores("0012.222222/2026-12")})
        terminou = threading.Event()

        def executar(lotes, emitir, controle):
            emitir("inicio", {"total": len(lotes)})
            emitir("lote_inicio", {"indice": 1, "total": 2, "dados": lotes[0]})
            emitir("lote_fim", {"indice": 1, "total": 2, "resultado": ResultadoLote(lotes[0], True, "a.pdf", "FULANO"),
                                "segundos": 3.2, "etapas": {"preparo": 1.0}})
            r2 = ResultadoLote(lotes[1], False, "", "", "TimeoutError: x")
            emitir("fim", {"resultados": [ResultadoLote(lotes[0], True), r2], "interrompido": False,
                           "pendentes": [lotes[1]], "total": 2})
            terminou.set()

        with mock.patch.object(motor, "executar", executar):
            r = M.chamar("iniciar")
            self.assertTrue(r["ok"])
            # enquanto roda, o SIGEF → SEI e o BB não conseguem o Chrome
            terminou.wait(5)
        for _ in range(50):
            if not M.executando():
                break
            threading.Event().wait(0.05)
        self.assertFalse(M.executando())
        self.assertTrue(modulos_janela.USO_DO_CHROME.acquire(blocking=False))   # devolvida no fim
        modulos_janela.USO_DO_CHROME.release()
        tipos = [d["evento"] for t, d in self.eventos if t == "dare_motor"]
        self.assertEqual(tipos, ["inicio", "lote_inicio", "lote_fim", "fim"])
        fim = [d for t, d in self.eventos if t == "dare_motor" and d["evento"] == "fim"][0]
        self.assertEqual(fim["pendentes"], 1)
        self.assertEqual(len(fim["lista"]["linhas"]), 1)          # só o pendente fica na lista
        self.assertEqual(fim["resultados"][0]["dados"]["cpf"], CPF)

    def test_nao_comeca_com_o_chrome_ocupado(self):
        M.chamar("salvar", {"valores": self.valores()})
        modulos_janela.USO_DO_CHROME.acquire()
        try:
            r = M.chamar("iniciar")
        finally:
            modulos_janela.USO_DO_CHROME.release()
        self.assertFalse(r["ok"]); self.assertIn("usando o Chrome", r["erro"])
        self.assertFalse(M.executando())


class TestPlanilha(Base):
    def test_importar_do_arquivo(self):
        from automacoes.dare import planilha_arquivo
        caminho = self.base / "lista.xlsx"
        planilha_arquivo.criar_modelo(caminho)
        import openpyxl
        wb = openpyxl.load_workbook(caminho)
        ws = wb.worksheets[0]
        ws.append(["0012.333333/2026-12", CNPJ, CPF, CNPJ, "102026", None, "150,00"])
        ws.append(["0012.444444/2026-12", CNPJ, "111.111.111-11", CNPJ, "102026", None, None])
        wb.save(caminho)
        with mock.patch.object(planilha_arquivo, "excel_disponivel", lambda: False):
            r = M.chamar("planilha_inicio")
            self.assertFalse(r["excel"])
            r = M._thread_planilha.executar(lambda: M._planilha("arquivo", {"caminho": str(caminho)}))
            self.assertTrue(r["ok"], r)
            aba = M.chamar("planilha_aba", {"aba": r["abas"][0]})
            self.assertTrue(aba["ok"], aba)
            self.assertFalse([c for c, o in aba["mapa"]["campos"].items()
                              if c in ("processo", "cpf") and not o["coluna"]])
            lido = M.chamar("planilha_ler", {**aba["mapa"], "de": aba["linhas"]["de"], "ate": aba["linhas"]["ate"]})
            self.assertTrue(lido["ok"], lido)
            self.assertEqual(lido["validas"], 2)                     # exemplo do modelo + a boa
            self.assertEqual(len(lido["problemas"]), 1)
            self.assertIn("CPF", lido["problemas"][0]["mensagem"])
            r = M.chamar("planilha_confirmar", {"substituir": True})
            self.assertEqual(r["n"], 2)
            self.assertTrue(all(l["origem"].startswith("linha ") for l in r["lista"]["linhas"]))


class TestOutrasTelas(Base):
    def test_arquivos_desempenho_configuracoes(self):
        pasta = Path(config.PASTA_PDF); pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "DARE_X.pdf").write_bytes(b"%PDF" + b"0" * 2000)
        a = M.chamar("arquivos")
        self.assertEqual(a["qtd"], 1)
        p = M.chamar("previa", {"criterio": "todos", "proteger": True})
        self.assertEqual(p["qtd"], 1)
        self.assertFalse(M.chamar("previa", {"criterio": "ate_data", "data": "31/02/2026"})["ok"])
        r = M.chamar("salvar_pref", {"limpeza_dias": "45", "aviso_tamanho_mb": "0"})
        self.assertEqual(r["pref"]["limpeza_dias"], 45)
        self.assertTrue(M.chamar("analise", {"apenas_sucesso": True})["ok"])
        c = M.chamar("configuracoes")
        self.assertTrue(c["recursos"]["GUIA_DE_USO.html"]); self.assertTrue(c["recursos"]["LICENCA.txt"])
        e = M.chamar("estado")
        self.assertTrue(e["ok"]); self.assertEqual(e["pdfs"]["qtd"], 1)


if __name__ == "__main__":
    unittest.main()
