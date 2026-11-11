"""
Testes da OB configurável (etapa_ob.py) e da tabela da OB
(configuracoes.py + conferência do SEI (1) + fluxo.gerar_obs).
"""
import json
from datetime import date

import pytest

from automacoes.anexar.automacao import configuracoes as cfg
from automacoes.anexar.automacao import dados_processo, etapa_ob, interacao
from automacoes.anexar.automacao import fluxo as main
from simulador_sigef import SigefSimulado
from test_ce_configuracoes import DADOS, PROCESSO, config_tmp, respostas  # noqa: F401

HOJE = date.today().strftime("%d%m%Y")
PP = "2026PP039778"


def com(**alteracoes) -> dict:
    config = {**cfg.PADRAO_GLOBAL, **cfg.PADRAO_OB}
    config.update(alteracoes)
    return config


# ============================================================ regras


class TestPadroes:
    def test_padrao_e_o_que_estava_no_codigo(self):
        assert cfg.config_ob() == {
            "unidade_gestora": "160001", "gestao": "00001", "banco_origem": "001",
            "agencia_origem": "2757-X", "tipo_ob": "2", "tipo_pagamento": "2",
            "fonte_recurso": "500001001",
            "observacao": "Regularização do valor pago na data de 01/07/2026 na conta do PROAFI",
        }
        assert cfg.problemas_ob(cfg.config_ob(), DADOS) == []
        assert "Descentralizada" in cfg.resumo_ob(cfg.config_ob())

    def test_arquivo_guarda_so_o_que_mudou(self, config_tmp):  # noqa: F811
        cfg.salvar_config_pp({**cfg.PADRAO_PP, "tipo_servico": "6"})
        cfg.salvar_config_ob(com(tipo_ob="3"))
        assert json.loads(config_tmp.read_text(encoding="utf-8")) == {
            "pp": {"tipo_servico": "6"}, "ob": {"tipo_ob": "3"},
        }

    def test_problemas(self):
        assert cfg.problemas_ob(com(agencia_origem=""), DADOS) == ["OB: Agência de origem em branco."]
        assert cfg.problemas_ob(cfg.PADRAO_OB, {**DADOS, "conta_ob": ""}) == ["OB: Conta OB em branco nos dados do processo."]
        assert "não existem: x" in cfg.problemas_ob(com(observacao="{x}"))[0]


# ============================================================ tabela da OB


def test_tabela_da_ob_mostra_estado():
    secao = cfg.secao("ob", DADOS, PROCESSO)
    campos = {campo["chave"]: campo for campo in secao["campos"]}
    assert secao["problemas"] == []
    assert campos["tipo_ob"]["padrao_texto"] == "Descentralizada" and campos["tipo_pagamento"]["padrao_texto"] == "Diversos"
    assert campos["agencia_origem"]["valor"] == "2757-X" and campos["fonte_recurso"]["valor"] == "500001001"
    assert "01/07/2026 na conta do PROAFI" in campos["observacao"]["valor"]
    automaticos = dict(secao["automaticos"])
    assert "105805" in automaticos["Conta de origem"] and automaticos["Id Uso"] == "1"


def test_tabela_da_ob_grava_tudo_e_restaura():
    cfg.salvar_secao("ob", {
        "tipo_ob": "4", "tipo_pagamento": "1", "banco_origem": "104", "agencia_origem": "0001-9",
        "fonte_recurso": "500001002", "observacao": "Regularização da parcela {parcela} -- {escola}",
    })
    assert cfg.config_ob() == {
        "unidade_gestora": "160001", "gestao": "00001", "banco_origem": "104",
        "agencia_origem": "0001-9", "tipo_ob": "4", "tipo_pagamento": "1",
        "fonte_recurso": "500001002", "observacao": "Regularização da parcela {parcela} -- {escola}",
    }
    with pytest.raises(cfg.ErroNasConfiguracoes) as erro:
        cfg.salvar_secao("ob", {"tipo_ob": "9", "observacao": "{nada}", "fonte_recurso": "50A", "agencia_origem": ""})
    assert set(erro.value.erros) == {"tipo_ob", "observacao", "fonte_recurso", "agencia_origem"}
    assert cfg.restaurar_padrao("ob") and cfg.config_ob() == com()


def test_conferencia_mostra_e_bloqueia_ob():
    pedido = dados_processo.pedido_conferencia({**DADOS, "conta_ob": ""}, PROCESSO)
    ob = next(c for c in pedido["configuracoes"] if c["secao"] == "ob")
    assert ob["resumo"].startswith("Descentralizada")
    assert "OB: Conta OB em branco nos dados do processo." in pedido["problemas"]
    assert pedido["botoes"][0]["desabilitado"] is True


def test_fluxo_pede_ajuste_antes_da_primeira_ob(monkeypatch):
    cfg.salvar_config_ob(com(agencia_origem=""))

    def arrumar(pedido):
        assert pedido["tipo"] == "configuracoes" and pedido["secao"] == "ob"
        cfg.salvar_secao("ob", {"agencia_origem": "2757-X"})
        return "pronto"

    pedidos = respostas(monkeypatch, "sim", arrumar)
    original = interacao._perguntar_pelo_aplicativo
    monkeypatch.setattr(interacao, "_perguntar_pelo_aplicativo",
                        lambda pedido: (lambda r: r(pedido) if callable(r) else r)(original(pedido)))
    main.garantir_config_ob(DADOS, PROCESSO)
    assert cfg.config_ob()["agencia_origem"] == "2757-X"
    assert pedidos[0]["titulo"] == "Falta ajustar a configuração da OB"
    assert [b["rotulo"] for b in pedidos[0]["botoes"]] == ["Abrir as configurações da OB", "Parar o processo aqui"]

    cfg.salvar_config_ob(com(agencia_origem=""))
    respostas(monkeypatch, "nao")
    with pytest.raises(etapa_ob.OBConfiguracaoIncompleta):
        main.garantir_config_ob(DADOS, PROCESSO)


# ============================================================ ponta a ponta (SIGEF simulado)


@pytest.fixture
def sigef(context, sessao_tmp):
    simulador = SigefSimulado({}, {})
    simulador.pps_para_ob = [("2026PP039777", "100,00"), (PP, "39,00")]
    simulador.instalar(context)
    return simulador


def test_ob_padrao_preenche_como_antes(context, sigef):
    ob = etapa_ob.executar_ob(context, PP, "105805", "3900", dict(DADOS))
    assert ob == "2026OB136475"
    assert sigef.obs_registradas == [{
        "data": HOJE, "ug": "160001", "gestao": "00001", "banco": "001", "agencia": "2757-X",
        "conta": "105805", "tipo_ob": "2", "tipo_pagamento": "2",
        "obs": "Regularização do valor pago na data de 01/07/2026 na conta do PROAFI", "pp": PP,
    }]
    assert sigef.buscas_pp_ob[0] == {"ug": "160001", "gestao": "00001", "iduso": "1", "fonte": "500001001"}


def test_ob_configurada(context, sigef):
    config = com(tipo_ob="3", tipo_pagamento="4", banco_origem="104", agencia_origem="1234-5",
                 fonte_recurso="500001002", unidade_gestora="160002",
                 observacao="Regularização da parcela {parcela} -- processo {processo}")
    etapa_ob.executar_ob(context, PP, "AB-9", "3900", {**DADOS, "processo": PROCESSO}, config)
    registrada = sigef.obs_registradas[0]
    assert (registrada["tipo_ob"], registrada["tipo_pagamento"], registrada["banco"], registrada["agencia"],
            registrada["conta"], registrada["ug"]) == ("3", "4", "104", "1234-5", "AB-9", "160002")
    assert registrada["obs"] == f"Regularização da parcela 7 -- processo {PROCESSO}"
    assert sigef.buscas_pp_ob[0]["fonte"] == "500001002" and sigef.buscas_pp_ob[0]["ug"] == "160002"


def test_ob_incompleta_nem_abre_o_sigef(context, sigef):
    with pytest.raises(etapa_ob.OBConfiguracaoIncompleta):
        etapa_ob.executar_ob(context, PP, "", "3900", dict(DADOS))
    assert sigef.requisicoes == [] and sigef.obs_registradas == []


def test_gerar_obs_do_main_usa_a_configuracao_salva(context, sigef):
    cfg.salvar_config_ob(com(tipo_pagamento="3"))
    lancamentos = [{"valor": "39,00", "valor_padronizado": "3900", "pp": PP}]
    main.gerar_obs(context, dict(DADOS), lancamentos, PROCESSO)
    assert lancamentos[0]["ob"] == "2026OB136475"
    assert sigef.obs_registradas[0]["tipo_pagamento"] == "3"


def test_global_vale_na_ob_do_sigef(context, sigef):
    cfg.salvar_config_global({"unidade_gestora": "160099", "gestao": "00007"})
    etapa_ob.executar_ob(context, PP, "105805", "3900", dict(DADOS))
    assert (sigef.obs_registradas[0]["ug"], sigef.obs_registradas[0]["gestao"]) == ("160099", "00007")
    assert (sigef.buscas_pp_ob[0]["ug"], sigef.buscas_pp_ob[0]["gestao"]) == ("160099", "00007")
