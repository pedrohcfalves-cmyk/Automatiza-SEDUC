"""
Testes do LOTE: 1 CE -> N lançamentos (cada um 1 NL + 1 PP) -> 1 OB.

    - NL: o número de cada NL é a linha NOVA da grade depois do
      "Confirmar" -- nunca "a primeira com aquele valor" (valores iguais
      no mesmo lote, ou NLs que já existiam na CE, não podem confundir).
    - OB: uma só para todas as PPs do lote; se faltar alguma PP na busca,
      nenhuma OB é gerada.
"""
import pytest

from automacoes.anexar.automacao import etapa_nl
from automacoes.anexar.automacao import etapa_ob
from automacoes.anexar.automacao import fluxo as main
from simulador_sigef import SigefSimulado
from test_ce_configuracoes import DADOS, PROCESSO, config_tmp  # noqa: F401

CE = "018705"


def lancamento(valor: str, ne: str = "540", **extra) -> dict:
    return {"valor": valor, "valor_padronizado": valor.replace(".", "").replace(",", ""),
            "nota_de_empenho": ne, **extra}


@pytest.fixture
def sigef(context, sessao_tmp, monkeypatch):
    monkeypatch.setattr(etapa_nl, "TIMEOUT_NL_NOVA_S", 4)
    simulador = SigefSimulado({}, {})
    simulador.instalar(context)
    return simulador


# ============================================================ identificação da NL (sem navegador)


class TestIdentificarNL:
    def test_pega_a_nova_e_nao_a_primeira_de_mesmo_valor(self):
        antes = [{"nl": "2026NL066235", "valor": "857,50"}]
        depois = antes + [{"nl": "2026NL066236", "valor": "857,50"}]
        assert etapa_nl._identificar_nl_nova(antes, depois, "85750") == "066236"

    def test_nenhuma_nova(self):
        antes = [{"nl": "2026NL066235", "valor": "857,50"}]
        assert etapa_nl._identificar_nl_nova(antes, antes, "85750") is None

    def test_nova_com_outro_valor_ainda_e_devolvida(self, capsys):
        depois = [{"nl": "2026NL066240", "valor": "800,00"}]
        assert etapa_nl._identificar_nl_nova([], depois, "85750") == "066240"
        assert "confira no SIGEF" in capsys.readouterr().out


# ============================================================ NL no SIGEF simulado


def test_lote_com_valores_iguais_recebe_nls_diferentes(context, sigef):
    lancamentos = [lancamento("857,50", "540"), lancamento("857,50", "541"), lancamento("39,00", "542")]
    etapa_nl.executar_nl_lote(context, CE, lancamentos, dict(DADOS))
    assert [item["nl"] for item in lancamentos] == ["066235", "066236", "066237"]
    assert [registro["ne"] for registro in sigef.nls_registradas] == ["540", "541", "542"]
    assert all(registro["retencao"] and registro["ce"] == CE for registro in sigef.nls_registradas)
    assert sigef.nl_lotes_finalizados == 1


def test_nl_que_ja_existia_na_ce_nao_e_confundida(context, sigef):
    sigef.nls_existentes = [("2026NL066000", "857,50")]     # mesma CE, mesmo valor, de antes
    lancamentos = [lancamento("857,50")]
    etapa_nl.executar_nl_lote(context, CE, lancamentos, dict(DADOS))
    assert lancamentos[0]["nl"] == "066235"


def test_nl_que_nao_foi_gerada_fica_none_e_o_resto_segue(context, sigef):
    sigef.nl_valores_que_falham = {"3900"}
    lancamentos = [lancamento("39,00"), lancamento("857,50")]
    etapa_nl.executar_nl_lote(context, CE, lancamentos, dict(DADOS))
    assert [item["nl"] for item in lancamentos] == [None, "066235"]


def test_retomada_nao_gera_nl_de_novo(context, sigef):
    lancamentos = [lancamento("857,50", nl="066100"), lancamento("39,00")]
    etapa_nl.executar_nl_lote(context, CE, lancamentos, dict(DADOS))
    assert [item["nl"] for item in lancamentos] == ["066100", "066235"]
    assert len(sigef.nls_registradas) == 1

    etapa_nl.executar_nl_lote(context, CE, lancamentos, dict(DADOS))   # tudo já tem NL
    assert len(sigef.nls_registradas) == 1 and sigef.nl_lotes_finalizados == 1


# ============================================================ 1 OB para o lote


@pytest.fixture
def sigef_ob(sigef):
    sigef.pps_para_ob = [
        ("2026PP039777", "100,00"), ("2026PP039778", "857,50"),
        ("2026PP039779", "857,50"), ("2026PP039780", "39,00"),
    ]
    return sigef


def test_uma_ob_para_todas_as_pps(context, sigef_ob):
    pps = [("2026PP039778", "85750"), ("2026PP039779", "85750"), ("2026PP039780", "3900")]
    ob = etapa_ob.executar_ob_lote(context, pps, "105805", dict(DADOS))
    assert ob == "2026OB136475"
    assert len(sigef_ob.obs_registradas) == 1
    assert sigef_ob.obs_registradas[0]["pp"] == "2026PP039778,2026PP039779,2026PP039780"


def test_pp_faltando_nao_gera_ob(context, sigef_ob):
    pps = [("2026PP039778", "85750"), ("2026PP039999", "1000")]
    with pytest.raises(etapa_ob.OBPPNaoEncontrada):
        etapa_ob.executar_ob_lote(context, pps, "105805", dict(DADOS))
    assert sigef_ob.obs_registradas == []


def test_valor_errado_nao_gera_ob(context, sigef_ob):
    with pytest.raises(etapa_ob.OBPPNaoEncontrada):
        etapa_ob.executar_ob_lote(context, [("2026PP039778", "85751")], "105805", dict(DADOS))
    assert sigef_ob.obs_registradas == []


def test_main_gera_uma_ob_e_anota_em_todos(context, sigef_ob):
    lancamentos = [
        lancamento("857,50", pp="2026PP039778"),
        lancamento("857,50", pp="2026PP039779"),
        lancamento("39,00", pp="2026PP039780"),
        lancamento("10,00"),                                   # sem PP: fica sem OB
    ]
    main.gerar_obs(context, dict(DADOS), lancamentos, PROCESSO)
    assert [item["ob"] for item in lancamentos] == ["2026OB136475"] * 3 + [None]
    assert len(sigef_ob.obs_registradas) == 1


def test_main_retomada_so_as_pps_sem_ob(context, sigef_ob):
    lancamentos = [
        lancamento("857,50", pp="2026PP039778", ob="2026OB136000"),   # já tinha OB
        lancamento("39,00", pp="2026PP039780"),
    ]
    main.gerar_obs(context, dict(DADOS), lancamentos, PROCESSO)
    assert [item["ob"] for item in lancamentos] == ["2026OB136000", "2026OB136475"]
    assert sigef_ob.obs_registradas[0]["pp"] == "2026PP039780"


def test_main_falha_na_ob_deixa_todos_pendentes(context, sigef_ob):
    lancamentos = [lancamento("857,50", pp="2026PP039778"), lancamento("1,00", pp="2026PP039999")]
    main.gerar_obs(context, dict(DADOS), lancamentos, PROCESSO)
    assert [item["ob"] for item in lancamentos] == [None, None]
    assert sigef_ob.obs_registradas == []


# ============================================================ download e colagem do lote (1 OB)


def test_download_e_colagem_do_lote_com_uma_ob(context, sessao_tmp, pasta_base, monkeypatch):
    import json
    import os

    from automacoes.anexar.automacao import etapa_listar_baixar as elb
    from automacoes.anexar.automacao import etapa_sei2 as sei2
    from simulador_sei import SeiSimulado
    from test_listar_baixar import cenario

    monkeypatch.setattr(elb, "TIMEOUT_GRADE_MS", 3000)
    monkeypatch.setattr(sei2, "ESPERAS_ENTRE_TENTATIVAS", (0, 0))
    lancamentos, pps, obs = cenario()
    for item in lancamentos:
        item["ob"] = "2026OB136475"                      # a MESMA OB para as 3 PPs
    for dados_pp in pps.values():
        dados_pp["ob"] = "2026OB136475"
    obs = {"2026OB136475": {"situacao": "10", "pps": list(pps)}}
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert all(item["anexo_baixado"] and item["rota_listagem"] == "Listar OB" for item in lancamentos)
    assert [d for d in sigef.downloads if d[0] == "OB"] == [("OB", "2026OB136475")]   # baixada 1 vez
    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    assert [numero for numero, _ in sessao["grupos_ob"]] == ["2026OB136475"]

    sei = SeiSimulado(PROCESSO)
    sei.instalar(context)
    sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, pasta_base=pasta_base)
    tipos = [d["tipo"] for d in sei.documentos]
    assert tipos.count("OB - Ordem Bancária de Regularização") == 1
    assert tipos.count("NL - Nota de Lançamento") == 3 and tipos.count("PP - Preparação de Pagamento") == 3
    assert os.path.exists(os.path.join(pasta_base, elb.nome_pasta_valido(PROCESSO), sei2.ARQUIVO_PROGRESSO_CONCLUIDO))
