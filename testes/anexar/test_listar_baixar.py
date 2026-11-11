"""
Testes da Etapa Anexar Documento (etapa_listar_baixar.py).

1) Funções puras: números, listagem, limpeza de dados velhos.
2) Ponta a ponta contra o SIGEF SIMULADO (simulador_sigef.py): listagem
   pela OB (igual ao LBA), reserva pela PP, falhas isoladas, retomada.
"""
import json
import os

import pytest

from automacoes.anexar.automacao import etapa_listar_baixar as elb
from simulador_sigef import SigefSimulado

PROCESSO = "0029.002180/2026-93"
CE = "018705"
VALORES = ["3.258,50", "857,50", "39,00"]


def cenario(qtd=3, situacao="10"):
    """Lançamentos como o main.py deixa depois de NL/PP/OB + o SIGEF correspondente."""
    lancamentos, pps, obs = [], {}, {}
    for i in range(qtd):
        valor = VALORES[i % len(VALORES)]
        pp = f"2026PP0397{78 + i}"
        nl = f"0662{35 + i}"
        ob = f"2026OB1364{75 + i}"
        lancamentos.append({
            "valor": valor,
            "valor_padronizado": valor.replace(".", "").replace(",", ""),
            "nota_de_empenho": "540",
            "nl": nl, "pp": pp, "ob": ob,
        })
        pps[pp] = {"ce": CE, "nl": f"2026NL{nl}", "ob": ob, "valor": valor}
        obs[ob] = {"situacao": situacao, "pps": [pp]}
    return lancamentos, pps, obs


@pytest.fixture(autouse=True)
def timeouts_curtos(monkeypatch):
    monkeypatch.setattr(elb, "TIMEOUT_GRADE_MS", 3000)
    monkeypatch.setattr(elb, "TIMEOUT_NL_MS", 5000)
    monkeypatch.setattr(elb, "TIMEOUT_OB_MS", 5000)


def _arquivos(pasta_base):
    pasta = os.path.join(pasta_base, elb.nome_pasta_valido(PROCESSO))
    return sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []


# ============================================================ funções puras


class TestNumeros:
    def test_sequencial(self):
        assert elb._sequencial("2026OB136475") == "136475"
        assert elb._sequencial("136475") == "136475"
        assert elb._sequencial("") == ""

    def test_completar(self):
        assert elb._completar_numero("066235", "NL", "2026") == "2026NL066235"
        assert elb._completar_numero("2026NL066235", "NL", "2025") == "2026NL066235"
        assert elb._completar_numero(" 2026 ob 136475 ", "OB", "2026") == "2026OB136475"
        assert elb._completar_numero(None, "OB", "2026") == ""
        assert elb._completar_numero("abc", "OB", "2026") == ""

    @pytest.mark.parametrize("a,b", [
        ("2026CE018705", "018705"), ("018705/2026", "18705"), ("2026PP039778", "039778"),
    ])
    def test_mesmo_documento(self, a, b):
        assert elb._mesmo_documento(a, b)

    @pytest.mark.parametrize("a,b", [("2026CE018705", "018706"), ("", ""), ("2026OB1", "")])
    def test_documentos_diferentes(self, a, b):
        assert not elb._mesmo_documento(a, b)

    def test_valor_em_centavos(self):
        assert elb._valor_em_centavos("3.258,50") == 325850
        assert elb._valor_em_centavos("325850") == 325850
        assert elb._valor_em_centavos("R$ 39,00") == 3900
        assert elb._valor_em_centavos("") is None


class TestListagem:
    def test_usa_os_numeros_gerados(self):
        lancamentos, _pps, _obs = cenario()
        listagem = elb.montar_listagem(lancamentos, CE)
        assert listagem["ce"] == CE
        assert [l["pp"] for l in listagem["itens"]] == ["2026PP039778", "2026PP039779", "2026PP039780"]
        assert [l["nl"] for l in listagem["itens"]] == ["2026NL066235", "2026NL066236", "2026NL066237"]
        assert list(listagem["por_ob"]) == ["2026OB136475", "2026OB136476", "2026OB136477"]
        assert listagem["avisos"] == []

    def test_faltas_viram_avisos(self):
        lancamentos, _pps, _obs = cenario()
        lancamentos[0]["pp"] = None          # sem PP
        lancamentos[1]["ob"] = None          # sem OB
        lancamentos[2]["nl"] = None          # sem NL
        lancamentos.append(dict(lancamentos[2]))   # PP repetida
        listagem = elb.montar_listagem(lancamentos, "")
        assert len(listagem["itens"]) == 2
        assert len(listagem["sem_pp"]) == 1
        assert [l["pp"] for l in listagem["sem_ob"]] == ["2026PP039779"]
        texto = " | ".join(listagem["avisos"])
        assert "sem PP" in texto and "sem OB" in texto and "sem NL" in texto
        assert "já está no lançamento" in texto and "Nenhuma CE" in texto

    def test_ob_compartilhada_agrupa(self):
        lancamentos, _pps, _obs = cenario()
        for item in lancamentos:
            item["ob"] = "136475"
        listagem = elb.montar_listagem(lancamentos, CE)
        assert list(listagem["por_ob"]) == ["2026OB136475"]
        assert len(listagem["por_ob"]["2026OB136475"]) == 3


class TestDadosVelhos:
    def test_pp_refeita_descarta_o_baixado(self):
        item = {"pp": "2026PP000002", "pp_baixada": "2026PP000001", "arquivos_pp": ["x"],
                "numero_ce": "1", "arquivos_ce": ["y"], "pp_dos_numeros": "2026PP000001",
                "numero_nl": "2026NL1", "arquivos_nl": ["z"]}
        elb._limpar_baixado_velho(item)
        assert "arquivos_pp" not in item and "arquivos_ce" not in item and "arquivos_nl" not in item

    def test_ob_nova_descarta_ob_velha(self):
        item = {"pp": "2026PP000001", "pp_baixada": "2026PP000001", "pp_dos_numeros": "2026PP000001",
                "ob": "2026OB000009", "numero_ob": "2026OB000008", "arquivos_ob": ["a"], "ob_baixada": "2026OB000008"}
        elb._limpar_baixado_velho(item)
        assert "numero_ob" not in item and "arquivos_ob" not in item

    def test_ce_nova_descarta_ce_velha(self):
        item = {"pp": "P", "pp_baixada": "P", "numero_ce": "018704", "arquivos_ce": ["a"]}
        elb._limpar_ce_velha(item, "018705")
        assert "numero_ce" not in item and "pp_baixada" not in item


# ====================================================== ponta a ponta (SIGEF simulado)


def test_modo_ob_baixa_tudo_com_os_numeros_gerados(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    arquivos = _arquivos(pasta_base)
    assert arquivos == sorted([
        "Despesa Certificada - CE 018705.jpg",
        "Nota de Lançamento - PP 2026PP039778.jpg",
        "Nota de Lançamento - PP 2026PP039779.jpg",
        "Nota de Lançamento - PP 2026PP039780.jpg",
        "Preparação de Pagamento - PP 2026PP039778.jpg",
        "Preparação de Pagamento - PP 2026PP039779.jpg",
        "Preparação de Pagamento - PP 2026PP039780.jpg",
        "Ordem Bancária - OB 2026OB136475_1.jpg", "Ordem Bancária - OB 2026OB136475_2.jpg",
        "Ordem Bancária - OB 2026OB136476_1.jpg", "Ordem Bancária - OB 2026OB136476_2.jpg",
        "Ordem Bancária - OB 2026OB136477_1.jpg", "Ordem Bancária - OB 2026OB136477_2.jpg",
    ])
    # A CE é a mesma nas 3 PPs: baixada uma vez só.
    assert [d for d in sigef.downloads if d[0] == "CE"] == [("CE", "2026CE018705")]
    # Listagem pela OB, como no LBA.
    assert "FINListarOrdemBancaria.aspx" in sigef.requisicoes
    assert "FINListarPreparacaoPagamento.aspx" in sigef.requisicoes   # só a conferência de sessão
    assert all(item["rota_listagem"] == "Listar OB" for item in lancamentos)
    assert all(item["anexo_baixado"] for item in lancamentos)
    assert all(item["numero_ce"] == CE for item in lancamentos)

    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    assert sessao["download_completo"] is True
    assert sessao["avisos_download"] == []
    assert [numero for numero, _ in sessao["grupos_ce"]] == [CE]
    assert [numero for numero, _ in sessao["grupos_ob"]] == ["2026OB136475", "2026OB136476", "2026OB136477"]
    assert [l["pp"] for l in sessao["listagem_download"]] == ["2026PP039778", "2026PP039779", "2026PP039780"]


def test_ob_em_outra_situacao_e_achada_sem_filtro(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario(situacao="5")   # recém-emitida, não "10"
    SigefSimulado(pps, obs).instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert all(item["rota_listagem"] == "Listar OB" for item in lancamentos)
    assert all(item["anexo_baixado"] for item in lancamentos)


def test_ob_que_nao_aparece_cai_para_listar_pp(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    obs["2026OB136476"]["listavel"] = False          # some de "Listar OB"
    SigefSimulado(pps, obs).instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    rotas = [item["rota_listagem"] for item in lancamentos]
    assert rotas == ["Listar OB", "Listar PP", "Listar OB"]
    assert all(item["anexo_baixado"] for item in lancamentos)


def test_pp_fora_da_grade_da_ob_avisa_e_baixa_pela_pp(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    obs["2026OB136477"]["pps"] = []                   # OB gerada não lista a PP
    SigefSimulado(pps, obs).instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert lancamentos[2]["rota_listagem"] == "Listar PP"
    assert lancamentos[2]["anexo_baixado"]
    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    assert any("não está na grade da OB" in aviso for aviso in sessao["avisos_download"])
    assert sessao["download_completo"] is False   # aviso pendente = conferir


def test_modo_pp(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE, modo="pp")

    assert "FINListarOrdemBancaria.aspx" not in sigef.requisicoes
    assert all(item["rota_listagem"] == "Listar PP" for item in lancamentos)
    assert all(item["anexo_baixado"] for item in lancamentos)
    assert len(_arquivos(pasta_base)) == 13


def test_nl_com_erro_nao_derruba_os_outros(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    sigef = SigefSimulado(pps, obs, nls={"2026NL066235", "2026NL066237"})   # a 066236 não aparece
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert [item["anexo_baixado"] for item in lancamentos] == [True, False, True]
    assert lancamentos[1]["arquivos_pp"] and lancamentos[1]["arquivos_ob"]
    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    assert any("NL 2026NL066236" in aviso for aviso in sessao["avisos_download"])
    assert sessao["download_completo"] is False


def test_divergencia_da_tela_vira_aviso_e_vale_o_gerado(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario(qtd=1)
    pps["2026PP039778"]["nl_tela"] = "2026NL099999"
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert lancamentos[0]["numero_nl"] == "2026NL066235"
    assert ("NL", "2026NL066235") in sigef.downloads
    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    assert any("a tela da PP mostra 2026NL099999" in aviso for aviso in sessao["avisos_download"])


def test_janela_da_pp_desviada_depois_da_ce(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario(qtd=2)
    SigefSimulado(pps, obs, desviar_pp_apos_ce=True).instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert all(item["anexo_baixado"] for item in lancamentos)
    assert "Preparação de Pagamento - PP 2026PP039778.jpg" in _arquivos(pasta_base)


def test_retomada_nao_abre_o_sigef_de_novo(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    sigef.requisicoes.clear()
    sigef.downloads.clear()
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert sigef.requisicoes == []
    assert all(item["anexo_baixado"] for item in lancamentos)


def test_retomada_baixa_so_o_que_faltou(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    sigef = SigefSimulado(pps, obs, nls={"2026NL066235", "2026NL066237"})
    sigef.instalar(context)
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)
    assert not lancamentos[1]["anexo_baixado"]

    sigef.nls.add("2026NL066236")     # o SIGEF voltou a mostrar a NL
    sigef.downloads.clear()
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert sigef.downloads == [("NL", "2026NL066236")]
    assert all(item["anexo_baixado"] for item in lancamentos)


def test_ce_nova_baixa_de_novo(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario(qtd=1)
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    pps["2026PP039778"]["ce"] = "018799"
    sigef.downloads.clear()
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce="018799")

    assert ("CE", "2026CE018799") in sigef.downloads
    assert lancamentos[0]["numero_ce"] == "018799"


def test_lancamento_sem_pp_nao_quebra(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    lancamentos[0]["pp"] = None
    SigefSimulado(pps, obs).instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert not lancamentos[0].get("anexo_baixado")
    assert lancamentos[1]["anexo_baixado"] and lancamentos[2]["anexo_baixado"]


def test_sem_nenhuma_pp_nao_abre_o_sigef(context, sessao_tmp, pasta_base):
    lancamentos, pps, obs = cenario()
    for item in lancamentos:
        item["pp"] = None
    sigef = SigefSimulado(pps, obs)
    sigef.instalar(context)

    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)

    assert sigef.requisicoes == []
