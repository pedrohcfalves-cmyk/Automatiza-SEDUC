"""Limpeza da pasta dos PDFs e preferências do aplicativo."""

import os
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from automacoes.dare import config, limpeza, preferencias


class TestLimpeza(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name) / "pdfs"
        self.pasta.mkdir()
        self.hist = Path(self.tmp.name) / "historico.csv"
        p = mock.patch.object(config, "ARQ_HISTORICO", self.hist)
        p.start()
        self.addCleanup(p.stop)
        agora = time.time()
        self.arquivos = {}
        for nome, dias, tam in (("novo.pdf", 1, 100), ("medio.pdf", 20, 200), ("velho.pdf", 90, 300),
                                ("falhou.pdf", 60, 400)):
            caminho = self.pasta / nome
            caminho.write_bytes(b"x" * tam)
            os.utime(caminho, (agora - dias * 86400, agora - dias * 86400))
            self.arquivos[nome] = caminho
        (self.pasta / "nao_e_pdf.txt").write_text("x")
        self.hist.write_text(
            "data_hora;status;pdf\n"
            f"01/01/2026 10:00:00;ERRO;{self.arquivos['falhou.pdf']}\n"
            f"01/01/2026 10:00:00;ERRO;{self.arquivos['velho.pdf']}\n"
            f"02/01/2026 10:00:00;SUCESSO;{self.arquivos['velho.pdf']}\n",
            encoding="utf-8-sig",
        )

    def test_lista_so_pdfs_e_marca_nao_anexados(self):
        lista = limpeza.listar_pdfs(self.pasta)
        self.assertEqual([a.nome for a in lista], ["novo.pdf", "medio.pdf", "falhou.pdf", "velho.pdf"])
        protegidos = {a.nome for a in lista if a.protegido}
        self.assertEqual(protegidos, {"falhou.pdf"})  # velho.pdf foi anexado numa nova tentativa

    def test_criterios(self):
        lista = limpeza.listar_pdfs(self.pasta)
        nomes = lambda xs: sorted(a.nome for a in xs)
        self.assertEqual(nomes(limpeza.selecionar(lista, "todos")), ["medio.pdf", "novo.pdf", "velho.pdf"])
        self.assertEqual(len(limpeza.selecionar(lista, "todos", proteger=False)), 4)
        self.assertEqual(nomes(limpeza.selecionar(lista, "mais_antigos", dias=30)), ["velho.pdf"])
        ate = (datetime.now() - timedelta(days=10)).date()
        self.assertEqual(nomes(limpeza.selecionar(lista, "ate_data", ate=ate)), ["medio.pdf", "velho.pdf"])
        with self.assertRaises(ValueError):
            limpeza.selecionar(lista, "ate_data")

    def test_apagar_de_vez(self):
        lista = limpeza.selecionar(limpeza.listar_pdfs(self.pasta), "mais_antigos", dias=10)
        with mock.patch.object(limpeza.os, "name", "posix"):
            r = limpeza.apagar(lista, lixeira=True)
        self.assertFalse(r.para_lixeira)
        self.assertEqual(r.apagados, 2)
        self.assertEqual(r.bytes_liberados, 500)
        self.assertTrue(self.arquivos["novo.pdf"].exists())
        self.assertTrue(self.arquivos["falhou.pdf"].exists())
        self.assertFalse(self.arquivos["velho.pdf"].exists())

    def test_resumo_e_tamanho(self):
        lista = limpeza.listar_pdfs(self.pasta)
        r = limpeza.resumo(lista)
        self.assertEqual((r["quantidade"], r["bytes"], r["protegidos"]), (4, 1000, 1))
        self.assertEqual(limpeza.tamanho_pasta(self.pasta), (4, 1000))
        self.assertEqual(limpeza.tamanho_pasta(self.pasta / "nao_existe"), (0, 0))

    def test_formatar_bytes(self):
        self.assertEqual(limpeza.formatar_bytes(500), "500 bytes")
        self.assertEqual(limpeza.formatar_bytes(1536), "1,5 KB")
        self.assertEqual(limpeza.formatar_bytes(5 * 1024 ** 3), "5,0 GB")


class TestPreferencias(unittest.TestCase):
    def test_salvar_carregar_e_aplicar(self):
        with TemporaryDirectory() as tmp, \
                mock.patch.object(config, "PASTA_DADOS", Path(tmp)), \
                mock.patch.object(config, "ARQ_PREFERENCIAS", Path(tmp) / "pref.json"), \
                mock.patch.object(config, "PASTA_PDF", config.PASTA_PDF):
            self.assertEqual(preferencias.carregar(), preferencias.Preferencias())
            pref = preferencias.Preferencias(pasta_pdf=str(Path(tmp) / "x"), limpeza_dias=7)
            preferencias.salvar(pref)
            lido = preferencias.carregar()
            self.assertEqual(lido, pref)
            preferencias.aplicar(lido)
            self.assertEqual(config.PASTA_PDF, Path(tmp) / "x")

    def test_valores_estranhos_sao_ignorados(self):
        pref = preferencias.Preferencias.de_dict({"limpeza_dias": "15", "usar_lixeira": "abc", "outro": 1})
        self.assertEqual(pref.limpeza_dias, 15)


if __name__ == "__main__":
    unittest.main()
