"""
O Cadastro de Credores dentro da Central, de ponta a ponta: a página do módulo (cadastro.js)
clicada como um usuário, falando com o Python de verdade (Api.cadastro -> janela/modulo_cadastro.py),
que cadastra no SIGEF simulado (sigef_simulado.py) pelo Chromium de depuração dos testes.

    python -m pytest testes/cadastro -q

Confere também o que muda por estar na Central: o ano do SIGEF da barra lateral e a regra de
uma automação por vez (USO_DO_CHROME).
"""
import builtins
import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "testes"))

# A pasta de dados da Central vai para um lugar temporário ANTES de importar a janela (ela abre o
# registro do dia ali e troca a saída e o input(); os originais voltam depois do import).
os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="janela_cadastro_"))
_saida, _erros, _input = sys.stdout, sys.stderr, builtins.input
import app_janela as A  # noqa: E402
sys.stdout, sys.stderr, builtins.input = _saida, _erros, _input

from automacoes import geral  # noqa: E402
from automacoes.cadastro import config  # noqa: E402
from automacoes.cadastro import navegador as navegador_cadastro  # noqa: E402
from automacoes.cadastro import planilha as planilha_cadastro  # noqa: E402
from conftest import fazer_login  # noqa: E402
from excel_falso import Aba, Excel, Pasta  # noqa: E402
from janela import modulos_janela  # noqa: E402
from ponte_pagina import PaginaComPython  # noqa: E402

M = A._modulo_cadastro()


def cpf_valido(base: str) -> str:
    """Completa 9 números com os dígitos verificadores (CPFs que o simulado ainda não conhece)."""
    numeros = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(n * peso for n, peso in zip(numeros, range(tamanho + 1, 1, -1)))
        numeros.append(soma * 10 % 11 % 10)
    return "".join(map(str, numeros))


def formatado(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


@pytest.fixture()
def tela(chromium, playwright, servidor):
    """A Central aberta, já logada no SIGEF simulado (o mesmo Chromium que o módulo usa)."""
    browser = playwright.chromium.connect_over_cdp(config.CDP_URL)
    aba = browser.contexts[0].new_page()
    fazer_login(aba)
    p = PaginaComPython(playwright, A)
    p.page.click('.modulo[data-modulo="cadastro"]')
    p.esperar("document.querySelector('#cad-corpo h1') !== null", mensagem="tela inicial do cadastro")
    yield p
    assert not p.erros_js, p.erros_js
    p.fechar()
    M._e.lotes.clear()
    M._e.refazer = None
    M._e.conferencia = "auto"


def entrar(p) -> None:
    p.page.click("#cad-comecar")
    p.esperar(lambda: "já estava aberto" in p.texto("#cad-situacao"), mensagem="navegador reaproveitado")
    p.page.click("#cad-entrei")
    p.esperar("document.querySelector('[data-ir=\"digitar\"]') !== null", mensagem="tela De onde vêm os dados?")


def test_digitar_colar_cadastrar_e_refazer_os_erros(tela, servidor):
    p = tela
    maria, jose = cpf_valido("731845920"), cpf_valido("731845921")
    servidor.estado.cpfs_invalidos.add("00000000191")
    entrar(p)
    assert p.page.evaluate("[...document.querySelectorAll('#cad-passos li')].map(l => l.className)")[:2] == ["feito", "atual"]

    p.page.click('[data-ir="digitar"]')
    p.esperar("document.querySelector('#cad-in-cpf') !== null")
    # Faltando campos: cada um fica em vermelho com o motivo (Formulario.ler da janela original).
    p.page.click("#cad-adicionar")
    p.esperar(lambda: "Preencha este campo." in p.texto('.cad-campo[data-campo="nome"]'))
    p.page.fill("#cad-in-cpf", formatado(maria))
    p.page.fill("#cad-in-nome", "MARIA DA CENTRAL")
    p.page.fill("#cad-in-banco", "banco do brasil")
    p.esperar(lambda: "001 - Banco do Brasil" in p.texto('.cad-campo[data-campo="banco"]'), mensagem="dica do banco")
    p.page.fill("#cad-in-agencia", "1234-5")
    p.page.fill("#cad-in-conta", "12.345-x")
    p.page.press("#cad-in-conta", "Enter")  # Enter no último campo adiciona
    p.esperar(lambda: "1 pessoa na lista" in p.texto("#cad-contador"))

    # CPF com dígito errado: pergunta antes (Adicionar mesmo assim / Corrigir o CPF).
    p.page.fill("#cad-in-cpf", "111.111.111-12")
    for campo, valor in (("nome", "X"), ("banco", "001"), ("agencia", "1"), ("conta", "2")):
        p.page.fill(f"#cad-in-{campo}", valor)
    p.page.click("#cad-adicionar")
    p.esperar(lambda: p.page.locator(".cad-modal").count() == 1, mensagem="Confira o CPF")
    assert "parece ter algum número errado" in p.texto(".cad-modal")
    p.page.click(".cad-modal >> text=Corrigir o CPF")
    assert "1 pessoa na lista" in p.texto("#cad-contador")

    # Colar uma lista: linha com problema avisa primeiro; "Adicionar mesmo assim" deixa ela de fora.
    p.page.click("#cad-colar")
    p.page.fill("#cad-colar-texto", f"{formatado(jose)}; JOSE DA CENTRAL; itau; 0001; 999-9\n"
                                    "000.000.001-91; CPF RECUSADO; 001; 1; 2\nlinha quebrada")
    p.page.click("#cad-colar-ok")
    p.esperar(lambda: "1 linha(s) com problema" in p.texto("#cad-colar-aviso"))
    p.page.click("#cad-colar-ok")
    p.esperar(lambda: "3 pessoas na lista" in p.texto("#cad-contador"))

    p.page.click("#cad-comecar-cad")
    p.esperar("document.querySelector('#cad-parar') !== null", mensagem="tela Cadastrando")
    # Terminou com um erro: fica no passo 3 e oferece refazer só ele (como a janela original).
    p.esperar(lambda: "Cadastro terminado" in p.texto("#cad-titulo"), segundos=90)
    assert "Com problema: 1" in p.texto("#cad-progresso-texto")
    linhas = p.page.locator(".cad-resultados tbody tr")
    assert linhas.count() == 3
    assert "✔ Cadastrado" in linhas.nth(0).inner_text() and "✔ Cadastrado" in linhas.nth(1).inner_text()
    assert "✖ Problema" in linhas.nth(2).inner_text()
    assert servidor.estado.credores[maria] == "MARIA DA CENTRAL"
    assert (maria, "001", "1234-5", "12.345-X") in servidor.estado.domicilios
    assert (jose, "341", "0001", "999-9") in servidor.estado.domicilios
    assert not modulos_janela.USO_DO_CHROME.locked()  # soltou o Chrome no fim

    p.page.click("#cad-ver")
    p.esperar(lambda: "Cadastro concluído" in p.texto("#cad-titulo"))
    assert p.page.locator("#cad-corpo .dare-kpi .val").all_inner_texts() == ["2", "0", "0", "1"]
    assert "Refazer as que deram erro (1)" in p.texto("#cad-refazer")
    assert "economia" in p.texto("#cad-corpo")  # a economia da sessão (estatísticas)

    # Refazer: só a pessoa com erro, com a numeração original (Nº 3).
    servidor.estado.cpfs_invalidos.discard("00000000191")
    p.page.click("#cad-refazer")
    p.esperar(lambda: "Cadastro concluído" in p.texto("#cad-titulo") and M._e.cadastrando is False, segundos=60)
    linhas = p.page.locator("#cad-corpo .dare-tabela tbody tr")
    assert linhas.count() == 1 and linhas.nth(0).inner_text().startswith("3")
    assert "✔ Cadastrado" in linhas.nth(0).inner_text()
    assert p.page.locator("#cad-refazer").count() == 0

    # Estatísticas: as duas sessões aparecem.
    p.page.click("#cad-estatisticas")
    p.esperar(lambda: "2 sessões" in p.texto("#cad-est-situacao"))
    assert p.page.locator("#cad-est-sessoes tbody tr").count() == 2


def test_conferir_cada_pessoa_pular_e_parar(tela, servidor):
    p = tela
    ana, bia = cpf_valido("731845922"), cpf_valido("731845923")
    entrar(p)
    p.page.click('[data-ir="digitar"]')
    p.page.click("#cad-colar")
    p.page.fill("#cad-colar-texto", f"{ana};ANA CONFERIDA;001;1;2\n{bia};BIA PULADA;001;1;2")
    p.page.click("#cad-colar-ok")
    p.esperar(lambda: "2 pessoas na lista" in p.texto("#cad-contador"))
    p.page.click('label.opcao:has(input[name="cad-conf"][value="manual"])')
    p.page.click("#cad-comecar-cad")

    # 1ª pessoa: "Cadastrar como credor?" -> Sim, e não perguntar mais sobre esta pessoa.
    p.esperar(lambda: p.page.locator(".cad-modal").count() == 1, segundos=30, mensagem="conferência")
    assert "Cadastrar esta pessoa como credor no SIGEF?" in p.texto(".cad-modal")
    assert "ANA CONFERIDA" in p.texto(".cad-modal")
    p.page.click('.cad-modal [data-r="t"]')
    # 2ª pessoa: Pular -> nada é gravado.
    p.esperar(lambda: p.page.locator(".cad-modal").count() == 1 and "BIA PULADA" in p.texto(".cad-modal"), segundos=60)
    p.page.click('.cad-modal [data-r="p"]')
    p.esperar(lambda: "Cadastro concluído" in p.texto("#cad-titulo"), segundos=60)
    assert p.page.locator("#cad-corpo .dare-kpi .val").all_inner_texts() == ["1", "0", "1", "0"]
    assert ana in servidor.estado.credores and bia not in servidor.estado.credores

    # Parar com a conferência aberta vale como "pular", e o cadastro termina interrompido.
    p.page.click("#cad-outro")
    p.page.click('[data-ir="digitar"]')
    p.page.click("#cad-colar")
    p.page.fill("#cad-colar-texto", f"{bia};BIA PARADA;001;1;2\n{cpf_valido('731845924')};NINGUEM;001;1;2")
    p.page.click("#cad-colar-ok")
    p.esperar(lambda: "2 pessoas na lista" in p.texto("#cad-contador"))
    p.page.click('label.opcao:has(input[name="cad-conf"][value="manual"])')
    p.page.click("#cad-comecar-cad")
    p.esperar(lambda: p.page.locator(".cad-modal").count() == 1, segundos=30)
    A.Api().cadastro("parar")  # o botão Parar fica atrás da janelinha; aqui direto pela porta
    p.esperar(lambda: "Cadastro interrompido" in p.texto("#cad-titulo"), segundos=60)
    assert bia not in servidor.estado.credores
    assert not modulos_janela.USO_DO_CHROME.locked()


def test_planilha_do_excel(tela, servidor, monkeypatch):
    p = tela
    carla = cpf_valido("731845925")
    aba = Aba("Folha", [
        ["RELAÇÃO DE SERVIDORES"], [],
        ["Nº", "ESCOLA", "MUNICÍPIO", "SERVIDOR", "CPF", "BANCO", "AGÊNCIA", "C/C"],
        [1, "EEEF A", "Porto Velho", "CARLA PLANILHA", carla, "Caixa", "0001", "123-4"],
        [2, "EEEF B", "Cacoal", "SEM BANCO", cpf_valido("731845926"), "Banco Imaginário", "1", "2"],
    ])
    pasta = Pasta("servidores.xlsx", [aba])
    monkeypatch.setattr(planilha_cadastro, "conectar_excel", lambda: Excel(pasta))
    M._e.excel = None
    entrar(p)
    p.page.click('[data-ir="planilha"]')
    # Uma planilha e uma aba só: já vêm escolhidas.
    p.esperar("!document.querySelector('#cad-continuar').disabled", mensagem="planilha escolhida")
    p.page.click("#cad-continuar")
    p.esperar("document.querySelector('#cad-primeira') !== null", mensagem="tela das colunas")
    assert "Encontrei os títulos das colunas na linha 3" in p.texto("#cad-corpo")
    assert p.page.input_value("#cad-primeira") == "4" and p.page.input_value("#cad-final") == "5"
    assert "CARLA PLANILHA" in p.texto('[data-exemplo="nome"]')
    # A coluna do resultado não pode ser uma das colunas com os dados.
    p.page.select_option("#cad-resultado", "E")
    assert "não pode ser uma das colunas" in p.texto("#cad-problema")
    assert p.page.is_disabled("#cad-comecar-cad")
    p.page.select_option("#cad-resultado", "J")
    # Trocar a primeira linha atualiza o exemplo (lido de novo da planilha).
    p.page.fill("#cad-primeira", "5")
    p.esperar(lambda: "SEM BANCO" in p.texto('[data-exemplo="nome"]'))
    p.page.fill("#cad-primeira", "4")
    p.esperar(lambda: "CARLA PLANILHA" in p.texto('[data-exemplo="nome"]'))

    p.page.click("#cad-comecar-cad")
    p.esperar(lambda: "Cadastro terminado" in p.texto("#cad-titulo"), segundos=90)
    assert aba.valor("J4") == "Operação realizada com sucesso."
    assert aba.valor("J5") == "ERRO: banco não reconhecido - Banco Imaginário"
    assert pasta.salvamentos == 2
    assert "corrija na planilha antes" in p.texto("#cad-agora")


def test_ano_do_sigef_e_uma_automacao_por_vez():
    try:
        geral._aplicar(2025)
        assert "/SIGEF2025/" in config.URL_MANTER_CREDOR and "/SIGEF2025/" in navegador_cadastro.URL_MANTER_CREDOR
        assert "/SIGEF2025/" in config.URL_INCLUIR_DOMICILIO
    finally:
        geral._aplicar(2026)
    assert "/SIGEF2026/" in navegador_cadastro.URL_MANTER_CREDOR
    assert str(config.PERFIL_CHROME) == r"C:\ChromeAutomacao"  # o perfil do Chrome da Central

    M._e.lotes[:] = [M.Lote(cpf_valido("731845927"), "X", "001", "1", "2")]
    modulos_janela.USO_DO_CHROME.acquire()
    try:
        r = A.Api().cadastro("comecar", {"modo": "lotes"})
        assert not r["ok"] and "Outra automação" in r["erro"]
        assert not M.executando()
    finally:
        modulos_janela.USO_DO_CHROME.release()
        M._e.lotes.clear()


def test_validacoes_da_porta():
    api = A.Api()
    r = api.cadastro("validar", {"valores": {"cpf": "1234567890123", "nome": "", "banco": "Banco Imaginário", "agencia": "1", "conta": "2"}})
    assert not r["ok"]
    assert r["erros"] == {"cpf": "O CPF precisa ter 11 números.", "nome": "Preencha este campo.",
                          "banco": "Banco não reconhecido. Digite o código (ex.: 001)."}
    # CPF curto ganha os zeros à esquerda que o Excel come (como no programa original).
    assert api.cadastro("validar", {"valores": {"cpf": "191"}})["lote"]["cpf"] == "00000000191"
    assert api.cadastro("banco", {"texto": "nubank"})["texto"] == "✔ 260 - Nubank"
    assert M.ler_minutos("4:30") == 270 and M.ler_minutos("4,5") == 270 and M.ler_minutos("x") is None
    assert M.problema_das_colunas({"cpf": 5}, 4, 3, 10).startswith("A linha de começo")
    assert M.problema_das_colunas({"cpf": 5}, 4, 9, 5).startswith("A coluna do resultado")
    assert M.problema_das_colunas({"cpf": 5}, 4, 9, 10) == ""
    assert api.cadastro("acao_que_nao_existe")["ok"] is False
    assert api.cadastro("responder", {"valor": "s"}) == {"ok": False}  # sem pergunta aberta, nada acontece
