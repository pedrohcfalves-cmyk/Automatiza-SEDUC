"""
Testes do que faz o programa funcionar em OUTROS computadores:
anexar/sistema/ambiente.py (acha o Chrome e as pastas) .
Na Central o instalador é o dela (instalador/ da raiz); os testes dos .bat e do Setup do
Anexar Documentos separado ficaram no programa antigo.

Nada aqui usa a internet nem precisa do Windows.
"""
import os
import sys

import pytest

from automacoes.anexar.sistema import ambiente

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # a pasta da Central


# ============================================================ ambiente.py


def _chrome_falso(pasta, *partes):
    caminho = pasta.joinpath(*partes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"MZ")
    return str(caminho)


def _sem_chrome_no_sistema(monkeypatch):
    monkeypatch.delenv("ANEXAR_CHROME", raising=False)
    monkeypatch.setattr(ambiente, "_candidatos_chrome", lambda: [])
    monkeypatch.setattr(ambiente, "_chrome_pelo_registro", lambda: "")
    monkeypatch.setattr(ambiente.shutil, "which", lambda nome: None)


def test_chrome_e_achado_em_qualquer_pasta_de_instalacao(tmp_path, monkeypatch):
    _sem_chrome_no_sistema(monkeypatch)
    assert ambiente.achar_chrome() is None

    so_para_mim = _chrome_falso(tmp_path, "AppData", "Local", "Google", "Chrome", "Application", "chrome.exe")
    monkeypatch.setattr(ambiente, "_candidatos_chrome", lambda: [str(tmp_path / "nao" / "existe.exe"), so_para_mim])
    assert ambiente.achar_chrome() == so_para_mim


def test_chrome_pelo_registro_e_variavel_de_ambiente(tmp_path, monkeypatch):
    _sem_chrome_no_sistema(monkeypatch)
    do_registro = _chrome_falso(tmp_path, "registro", "chrome.exe")
    monkeypatch.setattr(ambiente, "_chrome_pelo_registro", lambda: do_registro)
    assert ambiente.achar_chrome() == do_registro

    forcado = _chrome_falso(tmp_path, "forcado", "chrome.exe")
    monkeypatch.setenv("ANEXAR_CHROME", f'"{forcado}"')
    assert ambiente.achar_chrome() == forcado


def test_pasta_do_perfil_do_chrome(tmp_path, monkeypatch):
    forcada = tmp_path / "meu perfil"
    monkeypatch.setenv("ANEXAR_PERFIL_CHROME", str(forcada))
    assert ambiente.pasta_perfil_chrome() == str(forcada) and forcada.is_dir()

    monkeypatch.delenv("ANEXAR_PERFIL_CHROME")
    perfil = ambiente.pasta_perfil_chrome(criar=False)      # sem criar nada: só decide o caminho
    assert perfil.endswith("ChromeAutomacao")
    if os.name == "nt":
        assert perfil == ambiente.PERFIL_PADRAO_WINDOWS


def test_diagnostico_aponta_o_que_falta(tmp_path, monkeypatch):
    _sem_chrome_no_sistema(monkeypatch)
    monkeypatch.setattr(ambiente, "versao_da_biblioteca", lambda nome: None if nome == "pymupdf" else "1.0")
    monkeypatch.setattr(ambiente, "pasta_gravavel", lambda pasta: False)
    resultado = ambiente.diagnostico()
    ids = {problema["id"] for problema in resultado["problemas"]}
    assert ids == {"chrome", "bibliotecas", "pasta"}
    textos = " ".join(problema["texto"] for problema in resultado["problemas"])
    assert "google.com/chrome" in textos and "PyMuPDF" in textos and "instalador" in textos

    monkeypatch.setattr(ambiente, "achar_chrome", lambda: str(tmp_path / "chrome.exe"))
    monkeypatch.setattr(ambiente, "versao_da_biblioteca", lambda nome: "1.0")
    monkeypatch.setattr(ambiente, "pasta_gravavel", lambda pasta: True)
    assert ambiente.diagnostico()["problemas"] == []


def test_pasta_gravavel(tmp_path):
    assert ambiente.pasta_gravavel(str(tmp_path)) is True
    assert ambiente.pasta_gravavel(str(tmp_path / "nao_existe")) is False


def test_utils_usa_o_chrome_achado_e_avisa_quando_nao_existe(tmp_path, monkeypatch):
    from automacoes.anexar.automacao import utils

    monkeypatch.setattr(utils, "CAMINHO_CHROME_EXECUTAVEL", str(tmp_path / "nao_tem_chrome.exe"))
    with pytest.raises(Exception) as erro:
        utils._abrir_chrome_debug(9222)
    assert "não está instalado" in str(erro.value) and "google.com/chrome" in str(erro.value)


def test_formato_do_diagnostico():
    resultado = ambiente.diagnostico()
    for chave in ("python", "pasta_programa", "chrome", "perfil_chrome", "bibliotecas", "problemas", "site_chrome"):
        assert chave in resultado
    assert set(resultado["bibliotecas"]) == set(ambiente.BIBLIOTECAS)
