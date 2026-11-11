"""
Testes da PP configurável (etapa_pp.py) e da tabela da PP
(configuracoes.py + conferência do SEI (1)).
"""
import json

import pytest

from automacoes.anexar.automacao import configuracoes as cfg
from automacoes.anexar.automacao import dados_processo, etapa_pp
from simulador_sigef import SigefSimulado
from test_ce_configuracoes import DADOS, PROCESSO, config_tmp  # noqa: F401

CE = "018705"


def com(**alteracoes) -> dict:
    config = {**cfg.PADRAO_GLOBAL, **cfg.PADRAO_PP}
    config.update(alteracoes)
    return config


def lancamentos(qtd=1):
    return [
        {"valor": "39,00", "valor_padronizado": "3900", "nota_de_empenho": "540", "nl": f"0662{35 + i}"}
        for i in range(qtd)
    ]


# ============================================================ regras


class TestPadroes:
    def test_padrao_e_o_que_estava_no_codigo(self):
        config = cfg.config_pp()
        assert config == {
            "unidade_gestora": "160001", "gestao": "00001", "tipo_ordem_bancaria": "3",
            "tipo_servico": "10", "banco": "001", "agencia": "2757-X",
        }
        assert cfg.problemas_pp(config, DADOS) == []
        assert "Regularização" in cfg.resumo_pp(config) and "tudo padrão" in cfg.resumo_pp(config)

    def test_arquivo_guarda_so_o_que_mudou_e_nao_mexe_na_ce(self, config_tmp):  # noqa: F811
        cfg.salvar_config_ce({**cfg.PADRAO_CE, "tipo_documento": "99"})
        cfg.salvar_config_pp(com(tipo_servico="6"))
        assert json.loads(config_tmp.read_text(encoding="utf-8")) == {
            "ce": {"tipo_documento": "99"}, "pp": {"tipo_servico": "6"},
        }

    def test_conta_corrente_exige_banco_agencia_e_conta(self):
        assert cfg.problemas_pp(com(agencia=""), DADOS) == [
            "PP: Agência em branco (Crédito conta-corrente precisa de agência)."
        ]
        assert cfg.problemas_pp(cfg.PADRAO_PP, {**DADOS, "conta_pp": ""}) == [
            "PP: Conta PP em branco nos dados do processo."
        ]

    def test_outros_servicos_nao_exigem_conta(self):
        assert cfg.problemas_pp(com(tipo_servico="5", banco="", agencia=""), {**DADOS, "conta_pp": ""}) == []


# ============================================================ tabela da PP


def test_tabela_da_pp_mostra_estado():
    secao = cfg.secao("pp", DADOS, PROCESSO)
    campos = {campo["chave"]: campo for campo in secao["campos"]}
    assert secao["problemas"] == [] and campos["tipo_ordem_bancaria"]["padrao_texto"] == "Regularização"
    assert campos["tipo_servico"]["valor"] == "10"
    assert campos["agencia"]["valor"] == "2757-X"
    # Banco e Agência só com Crédito conta-corrente.
    assert campos["banco"]["mostrar_se"] == {"campo": "tipo_servico", "valores": ["10"]}
    assert "105805" in dict(secao["automaticos"])["Conta"]                 # Conta PP do processo
    assert "unidade_gestora" not in campos                                 # UG/Gestão são do Global


def test_tabela_da_pp_grava_e_restaura():
    secao = cfg.salvar_secao("pp", {"tipo_ordem_bancaria": "1", "tipo_servico": "10", "banco": "104", "agencia": "0001-9"})
    assert cfg.config_pp() == {
        "unidade_gestora": "160001", "gestao": "00001", "tipo_ordem_bancaria": "1",
        "tipo_servico": "10", "banco": "104", "agencia": "0001-9",
    }
    assert secao["alterados"] == 3
    with pytest.raises(cfg.ErroNasConfiguracoes) as erro:
        cfg.salvar_secao("pp", {"tipo_ordem_bancaria": "9"})              # código que não existe
    assert "tipo_ordem_bancaria" in erro.value.erros
    assert cfg.restaurar_padrao("pp") and cfg.config_pp() == com()


def test_outro_servico_guarda_o_banco_mas_nao_exige():
    cfg.salvar_secao("pp", {"tipo_servico": "6"})                         # banco/agência vieram escondidos
    config = cfg.config_pp()
    assert config["tipo_servico"] == "6" and config["banco"] == "001"     # guardado, só não aparece
    assert cfg.problemas_pp(config, {**DADOS, "conta_pp": ""}) == []


def test_conferencia_bloqueia_pp_incompleta():
    pedido = dados_processo.pedido_conferencia({**DADOS, "conta_pp": ""}, PROCESSO)
    assert "PP: Conta PP em branco nos dados do processo." in pedido["problemas"]
    assert pedido["botoes"][0]["desabilitado"] is True
    pp = next(c for c in pedido["configuracoes"] if c["secao"] == "pp")
    assert pp["resumo"].startswith("OB Regularização") and pp["problemas"]


# ============================================================ ponta a ponta (SIGEF simulado)


@pytest.fixture
def sigef(context, sessao_tmp):
    simulador = SigefSimulado({}, {})
    simulador.instalar(context)
    return simulador


def test_pp_padrao_preenche_como_antes(context, sigef):
    resultado = etapa_pp.executar_pp_lote(context, CE, lancamentos(2), "105805", dict(DADOS))
    assert [item["pp"] for item in resultado] == ["2026PP039778", "2026PP039779"]
    assert sigef.pps_registradas[0] == {
        "ug": "160001", "gestao": "00001", "nl": "066235", "ce": CE, "tipo_ob": "3", "servico": "10",
        "banco": "001", "agencia": "2757-X", "conta": "105805",     # banco limpo antes de digitar
    }
    assert sigef.pps_registradas[1]["nl"] == "066236"


def test_pp_configurada(context, sigef):
    config = com(tipo_ordem_bancaria="2", banco="104", agencia="1234-5", unidade_gestora="160002")
    etapa_pp.executar_pp_lote(context, CE, lancamentos(), "AB-12345", dict(DADOS), config)
    registrada = sigef.pps_registradas[0]
    assert (registrada["tipo_ob"], registrada["banco"], registrada["agencia"], registrada["conta"], registrada["ug"]) == (
        "2", "104", "1234-5", "AB-12345", "160002"
    )


def test_pp_outro_servico_com_campos_de_conta_na_tela(context, sigef):
    etapa_pp.executar_pp_lote(context, CE, lancamentos(), "105805", dict(DADOS), com(tipo_servico="6"))
    registrada = sigef.pps_registradas[0]
    assert registrada["servico"] == "6" and registrada["agencia"] == "2757-X"


def test_pp_outro_servico_sem_campos_de_conta(context, sigef):
    sigef.pp_esconde_conta_sem_credito = True
    etapa_pp.executar_pp_lote(context, CE, lancamentos(), "105805", dict(DADOS), com(tipo_servico="5"))
    registrada = sigef.pps_registradas[0]
    assert registrada["servico"] == "5" and registrada["banco"] is None


def test_pp_incompleta_nem_abre_o_sigef(context, sigef):
    with pytest.raises(etapa_pp.PPConfiguracaoIncompleta):
        etapa_pp.executar_pp_lote(context, CE, lancamentos(), "", dict(DADOS))
    assert sigef.requisicoes == [] and sigef.pps_registradas == []


def test_pp_usa_a_configuracao_salva(context, sigef):
    cfg.salvar_config_pp(com(tipo_ordem_bancaria="1"))
    etapa_pp.executar_pp_lote(context, CE, lancamentos(), "105805", dict(DADOS))
    assert sigef.pps_registradas[0]["tipo_ob"] == "1"


def test_global_vale_na_pp_do_sigef(context, sigef):
    cfg.salvar_config_global({"unidade_gestora": "160099", "gestao": "00007"})
    etapa_pp.executar_pp_lote(context, CE, lancamentos(), "105805", dict(DADOS))
    assert (sigef.pps_registradas[0]["ug"], sigef.pps_registradas[0]["gestao"]) == ("160099", "00007")
