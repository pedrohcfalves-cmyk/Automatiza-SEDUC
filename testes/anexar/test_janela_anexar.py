"""
O Anexar Documentos dentro da Central, de ponta a ponta: a página do módulo (anexar.js) clicada
como um usuário, falando com o Python de verdade (Api.anexar -> janela/modulo_anexar.py ->
nucleo.Execucao), que roda o executor num processo separado -- no Modo treino, que tem as mesmas
telas e não abre o Chrome nem mexe no SEI/SIGEF.

    python -m pytest testes/anexar -q

Confere também as telas Configurações (salvar, mudança não salva, voltar ao padrão),
Estatísticas, Relatório do mês e Ajuda, e a regra de uma automação por vez.
"""
import builtins
import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "testes"))

os.environ.setdefault("LBA_PASTA_DADOS", tempfile.mkdtemp(prefix="janela_anexar_"))
_saida, _erros, _input = sys.stdout, sys.stderr, builtins.input
import app_janela as A  # noqa: E402
sys.stdout, sys.stderr, builtins.input = _saida, _erros, _input

from automacoes.anexar.aplicativo import metricas, nucleo  # noqa: E402
from automacoes.anexar.automacao import configuracoes  # noqa: E402
from janela import modulos_janela  # noqa: E402
from ponte_pagina import PaginaComPython  # noqa: E402

M = A._modulo_anexar()


@pytest.fixture()
def tela(navegador, tmp_path, monkeypatch):
    """A Central aberta no módulo Anexar Documentos, com todos os dados numa pasta temporária."""
    monkeypatch.setenv("ANEXAR_PASTA_DADOS", str(tmp_path / "dados"))
    monkeypatch.setenv("ANEXAR_PASTA_RELATORIOS", str(tmp_path / "relatorios"))
    monkeypatch.setenv("ANEXAR_SESSAO_SIMULADA", str(tmp_path / "sessao_treino.json"))
    monkeypatch.setenv("ANEXAR_DEMO_PAUSA", "0.01")
    monkeypatch.setattr(configuracoes, "CAMINHO_CONFIG", str(tmp_path / "configuracoes.json"))
    monkeypatch.setattr(metricas, "PASTA_RELATORIOS", str(tmp_path / "relatorios"))
    monkeypatch.setattr(nucleo, "ARQUIVO_SESSAO", str(tmp_path / "sessao_atual.json"))
    p = PaginaComPython(navegador, A)  # o Chromium dos testes (conftest.py)
    p.page.click('.modulo[data-modulo="anexar"]')
    p.esperar("document.querySelector('#anx-corpo h1') !== null", mensagem="Início do Anexar")
    yield p
    M.encerrar()
    assert not p.erros_js, p.erros_js
    p.fechar()


def pedido(p, titulo: str, segundos=30):
    """Espera o quadro amarelo ("Sua vez") com este título."""
    p.esperar(lambda: p.page.locator('#anx-cp[data-estado="vez"]').count() == 1 and titulo in p.texto("#anx-cp h2"),
              segundos=segundos, mensagem=f"pedido “{titulo}”")


def test_processo_de_treino_do_comeco_ao_fim(tela):
    p = tela
    assert "O que você quer fazer agora?" in p.texto("#anx-corpo")
    assert not p.page.is_visible("#passos") and p.page.is_visible("#anx-nav")  # o menu do Anexar na faixa abaixo do topo
    p.page.check("#anx-treino")
    p.page.click('[data-atalho="processo"]')

    pedido(p, "Entre no SEI e no SIGEF")
    assert not modulos_janela.USO_DO_CHROME.locked()  # o treino não usa o Chrome
    assert p.page.is_disabled("#anx-treino")  # o Modo treino fica travado enquanto roda
    assert "SUA VEZ" in p.texto("#anx-cp").upper()
    p.page.click("#anx-cp >> text=Já entrei nos dois — continuar")

    pedido(p, "Qual é o processo?")
    p.page.fill('#anx-cp [data-chave="texto"]', "0029.002180/2026-93")
    p.page.press('#anx-cp [data-chave="texto"]', "Enter")  # ENTER não envia nada
    assert "Qual é o processo?" in p.texto("#anx-cp h2")
    p.page.click("#anx-cp >> text=Abrir o processo no SEI")

    # A tabela dos dados, de uma vez: com um campo faltando, volta com o erro ao lado.
    pedido(p, "Dados do processo")
    assert p.page.input_value('#anx-cp [data-chave="municipio"]') == "Porto Velho"
    p.page.fill('#anx-cp [data-chave="municipio"]', "")
    p.page.fill("#anx-lanc-linhas tr:nth-child(1) input >> nth=0", "100,00")
    p.page.fill("#anx-lanc-linhas tr:nth-child(1) input >> nth=1", "540")
    assert "Falta lançar R$ 200,00" in p.texto("#anx-soma")
    p.page.click("#anx-lanc-mais")
    p.page.fill("#anx-lanc-linhas tr:nth-child(2) input >> nth=0", "20000")
    assert "Sem vírgula: fica R$ 200,00" in p.texto("#anx-lanc-linhas tr:nth-child(2)")
    p.esperar(lambda: "✓ Confere" in p.texto("#anx-soma"))
    p.page.fill("#anx-lanc-linhas tr:nth-child(2) input >> nth=1", "541")
    p.page.click('#anx-cp [data-valor="conferir"]')
    p.esperar(lambda: "Falta arrumar 1 item" in p.texto("#anx-cp"), mensagem="erro do campo vazio")
    assert p.page.locator("#anx-cp .anx-erro-campo").count() == 1
    p.page.fill('#anx-cp [data-chave="municipio"]', "Porto Velho")
    assert p.page.locator("#anx-lanc-linhas tr").count() == 2  # os lançamentos voltaram como estavam
    p.page.click('#anx-cp [data-valor="conferir"]')

    pedido(p, "Confira os dados")
    assert "ESCOLA DE TREINO" in p.texto("#anx-cp") and "Lançamentos (2)" in p.texto("#anx-cp")
    assert "O que vai ser usado no SIGEF" in p.texto("#anx-cp")
    p.page.click('#anx-cp [data-valor="seguir"]')

    pedido(p, "Confira e assine no SEI", segundos=60)
    # O painel ao vivo mostra as NL, PP e OB que saíram.
    assert "066201" in p.texto("#anx-painel") and "2026OB012345" in p.texto("#anx-painel")
    passos = p.page.evaluate("[...document.querySelectorAll('#anx-passos li')].map(l => l.className)")
    assert passos[:6] == ["feito"] * 6 and passos[6] == "esperando"
    p.page.click("#anx-cp >> text=Terminei no SEI — continuar")

    pedido(p, "terminado (treino)")
    assert "Resumo — CE 018705" in p.texto("#anx-cp")
    p.page.click('#anx-cp [data-valor="nao"]')
    p.esperar(lambda: p.page.locator('#anx-cp[data-estado="fim-ok"]').count() == 1, segundos=30, mensagem="fim do treino")
    assert "Processo concluído" in p.texto("#anx-cp")
    assert "2 NL, 2 PP, 1 OB" in p.texto("#anx-cp")
    assert not p.page.is_disabled("#anx-treino")

    # O registro técnico (para o suporte) tem o que o programa escreveu.
    p.page.click("#anx-registro summary")
    p.esperar(lambda: "RESUMO" in p.texto("#anx-registro-texto"), mensagem="registro técnico")

    # Outro módulo aberto não perde nada: a página continua lendo o Anexar.
    p.page.click('.modulo[data-modulo="sei"]')
    p.page.click('.modulo[data-modulo="anexar"]')
    assert "Processo concluído" in p.texto("#anx-cp")


def test_sua_vez_aparece_com_outro_modulo_aberto_e_parar(tela):
    p = tela
    p.page.check("#anx-treino")
    p.page.click('[data-anx-ir="processo"]')
    p.page.click("#anx-comecar")
    pedido(p, "Entre no SEI e no SIGEF")
    p.page.click('.modulo[data-modulo="dare"]')
    p.page.click('.modulo[data-modulo="ne"]')
    p.esperar(lambda: p.page.locator('.modulo[data-modulo="anexar"] .rodando').count() == 1)
    assert p.page.locator('.modulo[data-modulo="anexar"].atencao').count() == 1  # o ponto fica amarelo
    p.page.click('.modulo[data-modulo="anexar"]')
    assert "Esperando você" in p.texto("#anx-situacao")
    p.page.click("#anx-parar")
    p.page.click(".anx-modal >> text=Sim, parar agora")
    p.esperar(lambda: p.page.locator('#anx-cp[data-estado="fim-atencao"]').count() == 1, segundos=30)
    assert "O programa foi parado" in p.texto("#anx-cp")
    assert p.page.locator('.modulo[data-modulo="anexar"] .rodando').count() == 0


def test_processo_de_verdade_respeita_uma_automacao_por_vez(tela):
    p = tela
    modulos_janela.USO_DO_CHROME.acquire()
    try:
        p.page.click('[data-anx-ir="processo"]')
        p.page.click("#anx-comecar")
        p.esperar(lambda: "Outra automação está usando o Chrome" in p.texto("#dare-toasts"))
        assert not M.executando()
    finally:
        modulos_janela.USO_DO_CHROME.release()


def test_configuracoes_salvar_mudanca_nao_salva_e_voltar_ao_padrao(tela, tmp_path):
    p = tela
    p.page.click('[data-anx-ir="configuracoes"]')
    p.esperar(lambda: p.page.locator(".anx-aba").count() == 5, mensagem="as 5 abas")
    assert [t.split("\n")[0] for t in p.page.locator(".anx-aba").all_inner_texts()] == ["Global", "CE", "NL", "PP", "OB"]
    p.page.click('.anx-aba[data-secao="pp"]')
    p.esperar("document.querySelector('#anx-cfg-agencia') !== null")
    p.page.fill("#anx-cfg-agencia", "0001-9")
    p.page.click("#anx-cfg-salvar")
    p.esperar(lambda: "Salvo. Já vale para o próximo processo." in p.texto("#anx-config"))
    assert "0001-9" in (tmp_path / "configuracoes.json").read_text(encoding="utf-8")

    # Mudança não salva: ao sair, pergunta (Continuar mexendo / Sair sem salvar / Salvar).
    p.page.fill("#anx-cfg-agencia", "9999-9")
    p.page.click('[data-anx-ir="inicio"]')
    p.esperar(lambda: p.page.locator(".anx-modal").count() == 1)
    assert "Salvar as mudanças?" in p.texto(".anx-modal")
    p.page.click(".anx-modal >> text=Continuar mexendo")
    assert p.page.input_value("#anx-cfg-agencia") == "9999-9"
    p.page.click("#anx-cfg-desfazer")
    assert p.page.input_value("#anx-cfg-agencia") == "0001-9"

    # Valor que não serve: volta em vermelho e nada é gravado.
    p.page.click('.anx-aba[data-secao="ob"]')
    p.esperar("document.querySelector('#anx-cfg-fonte_recurso') !== null")
    p.page.fill("#anx-cfg-fonte_recurso", "abc")
    p.page.click("#anx-cfg-salvar")
    p.esperar(lambda: p.page.locator("#anx-config .anx-erro-campo").count() >= 1)
    p.page.click("#anx-cfg-desfazer")

    p.page.click('.anx-aba[data-secao="pp"]')
    p.page.click("#anx-cfg-padrao")
    p.page.click(".anx-modal >> text=Sim, voltar ao padrão")
    p.esperar(lambda: "padrão" in p.texto('.anx-aba[data-secao="pp"]'))


def test_tempos_e_planilhas_e_ajuda(tela):
    p = tela
    p.page.click('[data-anx-ir="estatisticas"]')
    p.esperar(lambda: "Relatório geral" in p.texto("#anx-corpo"))  # os números foram para o relatório geral
    assert p.page.locator("#anx-corpo [data-relatorio-geral]").count() == 1
    assert p.page.locator("[data-estimativa]").count() == len(metricas.CATEGORIAS)
    p.page.fill('[data-estimativa="CE"]', "999")
    p.page.click("#anx-salvar-est")
    p.esperar(lambda: "o tempo vai de 0 a 240 minutos" in p.texto("#anx-est-msg"))
    assert p.page.locator('[data-anx-ir="relatorio"]').count() == 0
    p.page.click('[data-anx-ir="ajuda"]')
    p.esperar(lambda: "Todos os direitos reservados" in p.texto("#anx-corpo"))
    assert "Este computador" in p.texto("#anx-corpo") and "Google Chrome" in p.texto("#anx-corpo")
    # A letra é a da Central (botão Acessibilidade): sem botões de letra no módulo.
    assert p.page.locator("[data-anx-letra]").count() == 0
    p.page.click("#anx-como-usar")
    assert "Como usar: Ajuda e licença" in p.texto(".anx-modal")


def test_dados_ficam_fora_da_pasta_do_programa(tmp_path):
    # Sem ANEXAR_PASTA_DADOS, a Central usaria Documentos\\Anexar Documentos (nunca a pasta do código).
    assert M.PASTA_DADOS != os.path.join(RAIZ, "dados")
    antiga, nova = tmp_path / "antiga", tmp_path / "nova"
    (antiga / "relatorios").mkdir(parents=True)
    (antiga / "configuracoes_automacao.json").write_text("{}", encoding="utf-8")
    assert M._trazer_dados_antigos(str(antiga), str(nova)) is True
    assert (nova / "configuracoes_automacao.json").is_file() and (antiga / "configuracoes_automacao.json").is_file()
    assert M._trazer_dados_antigos(str(antiga), str(nova)) is False  # já existe: não mexe
