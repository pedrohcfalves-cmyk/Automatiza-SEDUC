"""
Testes da CE configurável (etapa_ce.py) e das tabelas de configuração
(configuracoes.py + quadro "Confira os dados" do SEI (1)).

1) Regras: padrões, Nota Fiscal, CPF/CNPJ, mês 13, modelos de texto, arquivo.
2) Tabelas: a tela mostra o ESTADO da CE, só o que faz sentido, e grava o que voltar.
3) Ponta a ponta: a CE preenchida no SIGEF simulado com cada configuração.
"""
import json
from datetime import date

import pytest

from automacoes.anexar.automacao import configuracoes as cfg
from automacoes.anexar.automacao import dados_processo, etapa_ce, interacao
from automacoes.anexar.automacao import utils
from simulador_sigef import SigefSimulado

PROCESSO = "0029.002180/2026-93"
ANO = str(date.today().year)
HOJE = date.today().strftime("%d%m%Y")

DADOS = {
    "cnpj_cpf": "03.508.155/0001-21",
    "municipio": "Espigão D'Oeste - RO",
    "escola": "CONSELHO ESCOLAR ASEEPNUUP",
    "conta_pp": "105805",
    "conta_ob": "105805",
    "parcela": "7",
    "mes_referencia": "10",
    "programa": "paanea",
    "valor_total": "4.155,00",
    "valor_total_padronizado": "415500",
    "valor_padronizado": "415500",
    "lancamentos": [{"valor": "4.155,00", "valor_padronizado": "415500", "nota_de_empenho": "540"}],
}


@pytest.fixture(autouse=True)
def config_tmp(tmp_path, monkeypatch):
    """configuracoes_automacao.json temporário (o real não é tocado)."""
    caminho = tmp_path / "configuracoes_automacao.json"
    monkeypatch.setattr(cfg, "CAMINHO_CONFIG", str(caminho))
    return caminho


def respostas(monkeypatch, *cliques):
    """
    Simula os cliques da pessoa, na ordem: cada item é o valor do botão (ou a
    resposta inteira de um formulário). Devolve a lista dos PEDIDOS que a
    tela recebeu, para o teste conferir o que foi mostrado.
    """
    fila = list(cliques)
    pedidos = []

    def tela(pedido):
        pedidos.append(pedido)
        if not fila:
            raise AssertionError(f"O programa pediu mais um clique do que o teste previa: {pedido.get('titulo')!r}")
        return fila.pop(0)

    monkeypatch.setattr(interacao, "_perguntar_pelo_aplicativo", tela)
    return pedidos


def com(**alteracoes) -> dict:
    config = {**cfg.PADRAO_GLOBAL, **cfg.PADRAO_CE}
    config.update(alteracoes)
    return config


# ============================================================ regras


class TestPadroes:
    def test_padrao_e_o_que_estava_no_codigo(self):
        config = cfg.config_ce()
        assert config["unidade_gestora"] == "160001"
        assert config["gestao"] == "00001"
        assert config["tipo_documento"] == "6"
        assert cfg.numero_documento_ce(DADOS) == f"paanea/{ANO}"
        assert set(config) == {"unidade_gestora", "gestao", "tipo_documento", "nf_subserie", "nf_serie",
                               "nf_modelo", "data_aceite", "data_apresentacao", "data_emissao", "observacao"}
        assert cfg.preencher_modelo(config["observacao"], DADOS, PROCESSO) == (
            "Regularização da 7 do paanea Em favor de CONSELHO ESCOLAR ASEEPNUUP, localizado "
            f"no município de Espigão D'Oeste - RO, referente ao processo {PROCESSO}."
        )
        assert [cfg.data_ce(config, chave) for chave, _r, _s in cfg.DATAS_CE] == [HOJE, HOJE, HOJE]
        assert cfg.problemas_ce(config, DADOS) == []

    def test_arquivo_guarda_so_o_que_mudou(self, config_tmp):
        cfg.salvar_config_ce(com(tipo_documento="99"))
        assert json.loads(config_tmp.read_text(encoding="utf-8")) == {"ce": {"tipo_documento": "99"}}
        assert cfg.config_ce()["tipo_documento"] == "99"

    def test_arquivo_estragado_volta_ao_padrao(self, config_tmp):
        # credor_tipo/atestado/numero_documento eram de uma versão anterior: ignorados.
        # UG/Gestão salvas dentro da CE também são ignoradas: agora são do Global.
        config_tmp.write_text('{"ce": {"credor_tipo": "cpf", "atestado": false, "gestao": "2"}}', encoding="utf-8")
        config = cfg.config_ce()
        assert "credor_tipo" not in config and "atestado" not in config and config["gestao"] == "00001"
        config_tmp.write_text("isso não é json", encoding="utf-8")
        assert cfg.config_ce() == com()


class TestNotaFiscal:
    @pytest.mark.parametrize("tipo", ["1", "2", "3", "4", "12"])
    def test_nota_fiscal_sem_campos_nao_passa(self, tipo):
        problemas = cfg.problemas_ce(com(tipo_documento=tipo))
        assert len(problemas) == 3 and all("SIGEF não gera a CE" in p for p in problemas)

    def test_nota_fiscal_completa_passa(self):
        assert cfg.problemas_ce(com(tipo_documento="1", nf_subserie="1", nf_serie="A", nf_modelo="55")) == []

    def test_tamanho_maximo(self):
        problemas = cfg.problemas_ce(com(tipo_documento="1", nf_subserie="12345678", nf_serie="A", nf_modelo="55"))
        assert problemas == ["Subsérie passa de 7 caracteres."]

    def test_outros_tipos_ignoram_campos_de_nf(self):
        assert cfg.problemas_ce(com(tipo_documento="99")) == []


class TestCredor:
    def test_detecta_sozinho(self):
        assert cfg.tipo_credor("03.508.155/0001-21") == "cnpj"
        assert cfg.tipo_credor("03508155000121") == "cnpj"
        assert cfg.tipo_credor("123.456.789-09") == "cpf"
        assert cfg.tipo_credor("123") is None

    def test_numero_estranho(self):
        assert "nem 11 (CPF)" in cfg.problemas_ce(cfg.PADRAO_CE, {**DADOS, "cnpj_cpf": "123"})[0]

    def test_programa_em_branco(self):
        assert "Programa em branco" in cfg.problemas_ce(cfg.PADRAO_CE, {**DADOS, "programa": ""})[0]


class TestMesEModelos:
    def test_mes_13(self):
        assert utils.padronizar_mes("13") == "13"
        assert cfg.nome_mes("13") == "Décimo Terceiro"
        with pytest.raises(ValueError):
            utils.padronizar_mes("14")

    def test_modelo_com_campo_inexistente(self):
        assert "não existem: nada" in cfg.problemas_ce(com(observacao="texto {nada}"))[0]

    def test_datas_separadas(self):
        config = com(data_aceite="01/07/2026", data_apresentacao="02/07/2026")
        assert cfg.data_ce(config, "data_aceite") == "01072026"
        assert cfg.data_ce(config, "data_apresentacao") == "02072026"
        assert cfg.data_ce(config, "data_emissao") == HOJE
        assert cfg.problemas_ce(com(data_apresentacao="31/02/2026")) == [
            "Data de Apresentação '31/02/2026' inválida (use dd/mm/aaaa)."
        ]
        assert "aceite 01/07/2026" in cfg.resumo_ce(config) and "apresentação 02/07/2026" in cfg.resumo_ce(config)

    def test_data_unica_da_versao_anterior_vira_as_tres(self, config_tmp):
        config_tmp.write_text('{"ce": {"data_documento": "05/05/2026"}}', encoding="utf-8")
        config = cfg.config_ce()
        assert (config["data_aceite"], config["data_apresentacao"], config["data_emissao"]) == ("05/05/2026",) * 3
        assert "data_documento" not in config


# ============================================================ tabelas da tela Configurações


def _campos(secao):
    return {campo["chave"]: campo for campo in secao["campos"]}


def test_tabela_da_ce_mostra_estado_e_o_automatico():
    secao = cfg.secao("ce", DADOS, PROCESSO)
    assert secao["titulo"].startswith("CE") and secao["problemas"] == [] and secao["alterados"] == 0
    campos = _campos(secao)
    assert campos["tipo_documento"]["valor"] == "6" and campos["tipo_documento"]["padrao_texto"] == "Aviso Débito Banco"
    assert ["1", "Nota Fiscal (pede Subsérie, Série e Modelo)"] in campos["tipo_documento"]["opcoes"]
    # Subsérie/Série/Modelo só aparecem com Nota Fiscal.
    assert campos["nf_serie"]["mostrar_se"] == {"campo": "tipo_documento", "valores": sorted(cfg.TIPOS_NOTA_FISCAL)}
    assert campos["data_aceite"]["tipo"] == "data" and campos["observacao"]["tipo"] == "modelo"
    automaticos = dict(secao["automaticos"])
    assert automaticos["Credor"] == "CNPJ 03.508.155/0001-21"          # detectado sozinho
    assert automaticos["Nº do Documento"] == f"paanea/{ANO}"
    assert automaticos["Unidade Gestora"].startswith("160001")          # vem do Global
    assert set(secao["campos_modelo"]) == cfg.CAMPOS_MODELO
    assert secao["valores_modelo"]["escola"] == "CONSELHO ESCOLAR ASEEPNUUP"


def test_salvar_a_ce_pela_tabela(config_tmp):
    secao = cfg.salvar_secao("ce", {"tipo_documento": "1", "nf_subserie": "A1", "nf_serie": "1", "nf_modelo": "55",
                                    "data_aceite": "2026-07-01", "data_apresentacao": "02072026", "data_emissao": ""})
    config = cfg.config_ce()
    assert (config["tipo_documento"], config["nf_subserie"], config["nf_serie"], config["nf_modelo"]) == ("1", "A1", "1", "55")
    assert (config["data_aceite"], config["data_apresentacao"], config["data_emissao"]) == ("01/07/2026", "02/07/2026", "")
    assert secao["problemas"] == [] and secao["alterados"] == 6
    assert json.loads(config_tmp.read_text(encoding="utf-8"))["ce"]["tipo_documento"] == "1"


def test_tabela_mostra_o_que_falta_na_nota_fiscal():
    cfg.salvar_secao("ce", {"tipo_documento": "2"})            # Nota Fiscal Avulsa, sem os campos
    problemas = cfg.secao("ce", DADOS, PROCESSO)["problemas"]
    assert any("Série da Nota Fiscal em branco" in p for p in problemas)


def test_tabela_recusa_valor_errado_sem_gravar_nada(config_tmp):
    with pytest.raises(cfg.ErroNasConfiguracoes) as erro:
        cfg.salvar_secao("ce", {"tipo_documento": "77", "data_aceite": "31/02/2026", "observacao": "texto {inexistente}",
                                "nf_serie": "12345678"})
    assert set(erro.value.erros) == {"tipo_documento", "data_aceite", "observacao", "nf_serie"}
    assert "{inexistente}" in erro.value.erros["observacao"]
    assert not config_tmp.exists()                              # nada foi gravado
    assert cfg.config_ce() == com()


def test_observacao_propria_e_voltar_ao_padrao():
    cfg.salvar_secao("ce", {"observacao": "Parcela {parcela} -- {escola}"})
    assert cfg.config_ce()["observacao"] == "Parcela {parcela} -- {escola}"
    secao = cfg.restaurar_padrao("ce")
    assert cfg.config_ce() == com() and secao["alterados"] == 0


def test_formulario_tem_todas_as_automacoes_na_ordem():
    secoes = cfg.formulario(DADOS, PROCESSO)
    assert [s["chave"] for s in secoes] == ["global", "ce", "nl", "pp", "ob"]
    nl = secoes[2]
    assert nl["editavel"] is False and nl["campos"] == [] and dict(nl["automaticos"])["Data de vencimento"] == "data de hoje"
    with pytest.raises(cfg.ErroNasConfiguracoes):
        cfg.salvar_secao("nl", {"x": "1"})
    assert "2757-X" in json.dumps(secoes) and "500001001" in json.dumps(secoes)


# ============================================================ "Confira os dados"


def test_conferencia_mostra_os_dados_e_as_configuracoes():
    pedido = dados_processo.pedido_conferencia({**DADOS}, PROCESSO)
    dados = dict(pedido["dados"])
    assert dados["Mês de referência"] == "10 - Outubro" and dados["Valor Total (CE)"] == "R$ 4.155,00"
    assert [c["secao"] for c in pedido["configuracoes"]] == ["global", "ce", "pp", "ob"]
    assert pedido["configuracoes"][0]["resumo"].startswith("UG 160001 | Gestão 00001")
    assert pedido["problemas"] == [] and pedido["lancamentos"]["comparacao"]["tipo"] == "ok"
    seguir = pedido["botoes"][0]
    assert seguir["valor"] == "seguir" and not seguir["desabilitado"]


def test_conferencia_bloqueia_ce_incompleta_ate_configurar(monkeypatch):
    cfg.salvar_config_ce(com(tipo_documento="1"))       # Nota Fiscal sem Série
    pedido = dados_processo.pedido_conferencia({**DADOS}, PROCESSO)
    assert pedido["botoes"][0]["desabilitado"] is True and pedido["tom"] == "atencao"
    assert any("Série da Nota Fiscal" in p for p in pedido["problemas"])

    # Na conversa: Configurações -> (a pessoa arruma na tela) -> Voltar -> Começar.
    def arrumar_e_voltar(pedido):
        cfg.salvar_secao("ce", {"tipo_documento": "1", "nf_subserie": "A1", "nf_serie": "1", "nf_modelo": "55"})
        return "pronto"

    formulario = {"botao": "conferir", "valores": {k: str(DADOS[k]) for k, *_ in dados_processo.CAMPOS},
                  "lancamentos": [{"valor": "4.155,00", "nota_de_empenho": "540"}]}
    pedidos = respostas(monkeypatch, formulario, "seguir", "configurar", arrumar_e_voltar, "seguir")
    original = interacao._perguntar_pelo_aplicativo

    def tela(pedido):
        resposta = original(pedido)
        return resposta(pedido) if callable(resposta) else resposta

    monkeypatch.setattr(interacao, "_perguntar_pelo_aplicativo", tela)
    dados = dados_processo.coletar(PROCESSO, {**DADOS})
    assert [p["tipo"] for p in pedidos] == ["formulario", "conferencia", "conferencia", "configuracoes", "conferencia"]
    assert pedidos[1]["botoes"][0]["desabilitado"] is True       # o 1o "seguir" não valia: pediu de novo
    assert pedidos[4]["botoes"][0]["desabilitado"] is False
    assert dados["lancamentos"][0]["valor_padronizado"] == "415500"


def test_conferencia_corrigir_volta_para_a_tabela(monkeypatch):
    formulario = {"botao": "conferir", "valores": {k: str(DADOS[k]) for k, *_ in dados_processo.CAMPOS},
                  "lancamentos": [{"valor": "4.155,00", "nota_de_empenho": "540"}]}
    corrigido = {**formulario, "valores": {**formulario["valores"], "escola": "OUTRA ESCOLA"}}
    pedidos = respostas(monkeypatch, formulario, "corrigir", corrigido, "seguir")
    dados = dados_processo.coletar(PROCESSO, {**DADOS})
    assert [p["tipo"] for p in pedidos] == ["formulario", "conferencia", "formulario", "conferencia"]
    assert dados["escola"] == "OUTRA ESCOLA"


# ============================================================ ponta a ponta (SIGEF simulado)


@pytest.fixture
def sigef(context, sessao_tmp):
    simulador = SigefSimulado({}, {})
    simulador.instalar(context)
    return simulador


def test_ce_padrao_preenche_como_antes(context, sigef):
    ce = etapa_ce.executar_ce(context, PROCESSO, dict(DADOS))
    assert ce == "018705"
    assert sigef.ces_registradas == [{
        "ug": "160001", "gestao": "00001", "tipo": "6", "subserie": "", "serie": "", "modelo": "",
        "numdoc": f"paanea/{ANO}", "atestado": True,
        "dt_aceite": HOJE, "dt_apresentacao": HOJE, "dt_emissao": HOJE, "mes": "10",
        "obs": cfg.preencher_modelo(cfg.OBSERVACAO_PADRAO, DADOS, PROCESSO),
        "credor": "cnpj:03.508.155/0001-21", "valor": "415500",
    }]
    assert json.loads(open(utils.CAMINHO_SESSAO, encoding="utf-8").read())["ce"] == "018705"


def test_ce_nota_fiscal(context, sigef):
    config = com(tipo_documento="12", nf_subserie="1", nf_serie="A1", nf_modelo="55")
    etapa_ce.executar_ce(context, PROCESSO, dict(DADOS), config)
    registrada = sigef.ces_registradas[0]
    assert (registrada["tipo"], registrada["subserie"], registrada["serie"], registrada["modelo"]) == ("12", "1", "A1", "55")


def test_ce_nota_fiscal_incompleta_nem_abre_o_sigef(context, sigef):
    with pytest.raises(etapa_ce.CEConfiguracaoIncompleta):
        etapa_ce.executar_ce(context, PROCESSO, dict(DADOS), com(tipo_documento="1"))
    assert sigef.ces_registradas == []
    assert "FINManterDespesaCertificada.aspx" in sigef.requisicoes or sigef.requisicoes == []


def test_ce_credor_cpf_mes_13_e_textos_proprios(context, sigef):
    dados = {**DADOS, "cnpj_cpf": "123.456.789-09", "mes_referencia": "13"}
    config = com(observacao="13º -- {escola} ({mes_nome})",
                 data_aceite="01/07/2026", data_apresentacao="02/07/2026", unidade_gestora="160099")
    etapa_ce.executar_ce(context, PROCESSO, dados, config)
    registrada = sigef.ces_registradas[0]
    assert registrada["credor"] == "cpf:12345678909"
    assert registrada["mes"] == "13"
    assert registrada["obs"] == "13º -- CONSELHO ESCOLAR ASEEPNUUP (Décimo Terceiro)"
    assert registrada["numdoc"] == f"paanea/{ANO}"            # sempre {programa}/{ano}
    assert (registrada["dt_aceite"], registrada["dt_apresentacao"], registrada["dt_emissao"]) == ("01072026", "02072026", HOJE)
    assert registrada["atestado"] is True                      # sempre marcado
    assert registrada["ug"] == "160099"


def test_ce_usa_a_configuracao_salva(context, sigef):
    cfg.salvar_config_ce(com(tipo_documento="99"))
    etapa_ce.executar_ce(context, PROCESSO, dict(DADOS))
    assert sigef.ces_registradas[0]["tipo"] == "99"


# ============================================================ Global (UG / Gestão de todas as etapas)


def test_global_padrao_e_tabela(config_tmp):
    assert cfg.config_global() == {"unidade_gestora": "160001", "gestao": "00001"}
    cfg.salvar_secao("global", {"unidade_gestora": "160099", "gestao": "00007"})
    assert json.loads(config_tmp.read_text(encoding="utf-8")) == {"global": {"unidade_gestora": "160099", "gestao": "00007"}}
    # Muda todas as etapas de uma vez.
    for config in (cfg.config_ce(), cfg.config_pp(), cfg.config_ob()):
        assert (config["unidade_gestora"], config["gestao"]) == ("160099", "00007")
    assert cfg.gestao_sem_zeros("00007") == "7"
    with pytest.raises(cfg.ErroNasConfiguracoes) as erro:
        cfg.salvar_secao("global", {"unidade_gestora": "16A001", "gestao": ""})
    assert set(erro.value.erros) == {"unidade_gestora", "gestao"}
    assert cfg.restaurar_padrao("global")["alterados"] == 0 and cfg.config_global() == cfg.PADRAO_GLOBAL


def test_global_aparece_na_conferencia():
    pedido = dados_processo.pedido_conferencia({**DADOS}, PROCESSO)
    assert pedido["configuracoes"][0]["resumo"] == "UG 160001 | Gestão 00001 | padrão"


def test_global_vale_na_ce_do_sigef(context, sigef):
    cfg.salvar_config_global({"unidade_gestora": "160099", "gestao": "00007"})
    etapa_ce.executar_ce(context, PROCESSO, dict(DADOS))
    assert (sigef.ces_registradas[0]["ug"], sigef.ces_registradas[0]["gestao"]) == ("160099", "00007")
