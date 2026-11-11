"""
Testes da Etapa SEI (2) (etapa_sei2.py) -- a "colagem".

1) Funções puras: divisão em partes (2 MB), recusa por tamanho, processo,
   conferência da colagem, origem dos arquivos (memória/sessão/pasta),
   progresso/retomada.
2) Ponta a ponta: SIGEF simulado -> download -> SEI simulado (CKEditor
   de verdade): ordem CE -> NL -> PP -> OB, Restrito + Documento
   Preparatório, número da PP, imagens gravadas, retomada sem duplicar.
"""
import json
import os
import random

import pytest
from PIL import Image

from automacoes.anexar.automacao import etapa_listar_baixar as elb
from automacoes.anexar.automacao import etapa_sei2 as sei2
from simulador_sei import SeiSimulado
from simulador_sigef import SigefSimulado
from test_listar_baixar import CE, PROCESSO, cenario


@pytest.fixture(autouse=True)
def sem_esperas(monkeypatch):
    monkeypatch.setattr(sei2, "ESPERAS_ENTRE_TENTATIVAS", (0, 0))
    monkeypatch.setattr(elb, "TIMEOUT_GRADE_MS", 3000)


def _jpg(caminho, largura=400, altura=560, ruido=False):
    if ruido:
        dados = bytes(random.getrandbits(8) for _ in range(largura * altura * 3))
        imagem = Image.frombytes("RGB", (largura, altura), dados)
    else:
        imagem = Image.new("RGB", (largura, altura), (255, 255, 255))
    imagem.save(caminho, "JPEG", quality=95)
    return str(caminho)


# ============================================================ funções puras


class TestDivisaoEmPartes:
    def test_cabe_tudo(self):
        assert sei2._dividir_em_partes([100, 200, 300], 1000) == [[0, 1, 2]]

    def test_equilibrada(self):
        assert sei2._dividir_em_partes([300] * 8, 1300) == [[0, 1, 2, 3], [4, 5, 6, 7]]

    def test_pagina_grande_sozinha(self):
        assert sei2._dividir_em_partes([100, 5000, 100], 1000) == [[0], [1], [2]]

    def test_vazia(self):
        assert sei2._dividir_em_partes([], 1000) == []

    def test_mantem_ordem_e_todas_as_paginas(self):
        tamanhos = [random.randint(50, 600) for _ in range(30)]
        partes = sei2._dividir_em_partes(tamanhos, 1500)
        assert [i for parte in partes for i in parte] == list(range(30))
        assert all(sum(tamanhos[i] for i in parte) <= 1500 for parte in partes if len(parte) > 1)


def test_erro_de_tamanho():
    assert sei2._eh_erro_de_tamanho("O documento com imagem NÃO pode exceder 2MB. Utilize a opção Documento Externo.")
    assert not sei2._eh_erro_de_tamanho("Falha de comunicação com o servidor.")


@pytest.mark.parametrize("texto", ["0029002180202693", "0029.002180.2026-93", "0029.002180-2026-93", "0029.002180/2026-93"])
def test_normalizar_processo(texto):
    assert sei2.normalizar_processo_sei(texto) == "0029.002180/2026-93"


def test_resolver_pela_pasta_com_nomes_antigos(tmp_path, sessao_tmp):
    """A pasta real do usuário tem nomes antigos ("Despesa Certificada.jpg", "Ordem Bancária_1.jpg")."""
    pasta = tmp_path / elb.nome_pasta_valido(PROCESSO)
    pasta.mkdir()
    for nome in ["Despesa Certificada.jpg", "Ordem Bancária_1.jpg", "Ordem Bancária_2.jpg",
                 "Nota de Lançamento - PP 052337.jpg", "Preparação de Pagamento - PP 052337.jpg"]:
        _jpg(pasta / nome)
    pacote = sei2.resolver_dados_da_etapa_anterior(PROCESSO, None, pasta_base=str(tmp_path))
    assert pacote["origem"] == "pasta"
    assert len(pacote["grupos_ce"]) == 1 and len(pacote["grupos_ob"]) == 1
    assert len(pacote["grupos_ob"][0][1]) == 2
    assert pacote["grupos_nl"][0][0] == "052337" and pacote["grupos_pp"][0][0] == "052337"


def test_resolver_ignora_sessao_de_outro_processo(tmp_path, sessao_tmp):
    sessao_tmp.write_text(json.dumps({"download_processo": "0029.999999/2026-11", "grupos_ce": [["1", ["x.jpg"]]]}))
    pacote = sei2.resolver_dados_da_etapa_anterior(PROCESSO, None, pasta_base=str(tmp_path))
    assert pacote["origem"] == "pasta"


def test_conferir_colagem_aponta_o_que_falta():
    pacote = {
        "listagem": [
            {"pp": "2026PP000001", "nl": "2026NL000011", "ob": "2026OB000021"},
            {"pp": "2026PP000002", "nl": "2026NL000012", "ob": "2026OB000022"},
        ],
        "grupos_ce": [("018705", ["ce.jpg"])],
        "grupos_nl": [("2026PP000001", ["a"])],
        "grupos_pp": [("2026PP000001", ["b"]), ("2026PP000002", ["c"])],
        "grupos_ob": [("2026OB000021", ["d"])],
    }
    avisos = sei2.conferir_colagem(pacote)
    assert len(avisos) == 2
    assert "NL 2026NL000012" in avisos[0] and "OB 2026OB000022" in avisos[1]


class TestProgresso:
    def test_retoma_e_conclui(self, tmp_path):
        progresso = sei2.ProgressoSei(PROCESSO, "2026PP1, 2026PP2", pasta_base=str(tmp_path))
        progresso.marcar("CE 018705", "salvo")
        progresso.marcar("NL 2026PP1", "criado", url_editor="http://x")

        de_novo = sei2.ProgressoSei(PROCESSO, "2026PP1, 2026PP2", pasta_base=str(tmp_path))
        assert de_novo.retomando and de_novo.estado("CE 018705")["estado"] == "salvo"

        outro_lote = sei2.ProgressoSei(PROCESSO, "2026PP9", pasta_base=str(tmp_path))
        assert not outro_lote.retomando

        de_novo.concluir(["2026OB000021", "2026OB000022"])
        assert sei2.ob_ja_concluida(PROCESSO, "000021", pasta_base=str(tmp_path))
        assert not sei2.ProgressoSei(PROCESSO, "2026PP1, 2026PP2", pasta_base=str(tmp_path)).retomando

    def test_tentativa_velha_nao_e_retomada(self, tmp_path):
        progresso = sei2.ProgressoSei(PROCESSO, "L", pasta_base=str(tmp_path))
        progresso.marcar("CE 1", "salvo")
        velho = os.path.getmtime(progresso.caminho) - (sei2.PRAZO_RETOMADA_HORAS + 1) * 3600
        os.utime(progresso.caminho, (velho, velho))
        assert not sei2.ProgressoSei(PROCESSO, "L", pasta_base=str(tmp_path)).retomando


def test_planejar_partes_divide_documento_grande(tmp_path, monkeypatch):
    arquivos = [_jpg(tmp_path / f"p{i}.jpg", 700, 900, ruido=True) for i in range(6)]
    preparados = [sei2._preparar_imagem_para_insercao(c) for c in arquivos]   # ≤ 250 KB cada
    tamanho = sum(sei2._tamanho_estimado_imagem(c) for c in preparados)
    monkeypatch.setattr(sei2, "LIMITE_DOCUMENTO_BYTES", tamanho // 2 + sei2.FOLGA_HTML_DOCUMENTO_BYTES)
    partes = sei2._planejar_partes(arquivos)
    assert len(partes) >= 2
    assert sum(len(p) for p in partes) == 6


# ====================================================== ponta a ponta


def _baixar(context, sessao_tmp, pasta_base, qtd=3):
    lancamentos, pps, obs = cenario(qtd=qtd)
    SigefSimulado(pps, obs).instalar(context)
    elb.executar_anexar_lote(context, PROCESSO, lancamentos, pasta_base=pasta_base, ce=CE)
    return lancamentos


def test_fluxo_completo_download_e_colagem(context, sessao_tmp, pasta_base):
    _baixar(context, sessao_tmp, pasta_base)
    sei = SeiSimulado(PROCESSO)
    sei.instalar(context)

    avisos = []
    sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, avisos_saida=avisos, pasta_base=pasta_base)

    tipos = [(d["tipo"], d["numero"]) for d in sei.documentos]
    assert tipos == [
        ("Despesa Certificada", ""),
        ("NL - Nota de Lançamento", ""), ("NL - Nota de Lançamento", ""), ("NL - Nota de Lançamento", ""),
        ("PP - Preparação de Pagamento", "039778"),
        ("PP - Preparação de Pagamento", "039779"),
        ("PP - Preparação de Pagamento", "039780"),
        ("OB - Ordem Bancária de Regularização", ""),
        ("OB - Ordem Bancária de Regularização", ""),
        ("OB - Ordem Bancária de Regularização", ""),
    ]
    assert all(d["nivel"] == "restrito" and d["hipotese"] == "3" and d["texto_inicial"] == "N" for d in sei.documentos)
    # Imagens realmente gravadas (o modelo padrão foi apagado).
    assert [SeiSimulado.qtd_imagens(d) for d in sei.documentos] == [1, 1, 1, 1, 1, 1, 1, 2, 2, 2]
    assert all("Modelo padrão" not in d["html"] for d in sei.documentos)
    assert 'width="800"' in sei.documentos[0]["html"] and 'width="1000"' in sei.documentos[-1]["html"]
    assert avisos == []

    pasta = os.path.join(pasta_base, elb.nome_pasta_valido(PROCESSO))
    assert not os.path.exists(os.path.join(pasta, sei2.ARQUIVO_PROGRESSO))
    concluido = json.loads(open(os.path.join(pasta, sei2.ARQUIVO_PROGRESSO_CONCLUIDO), encoding="utf-8").read())
    assert concluido["obs"] == ["2026OB136475", "2026OB136476", "2026OB136477"]


def test_queda_no_salvar_tenta_de_novo_no_mesmo_documento(context, sessao_tmp, pasta_base):
    _baixar(context, sessao_tmp, pasta_base, qtd=1)
    sei = SeiSimulado(PROCESSO, falhas_salvar={2: 1})   # o 2º documento falha uma vez
    sei.instalar(context)

    sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, pasta_base=pasta_base)

    assert len(sei.documentos) == 4          # CE, NL, PP, OB -- nenhum duplicado
    assert all(SeiSimulado.qtd_imagens(d) >= 1 for d in sei.documentos)


def test_interrompido_retoma_sem_duplicar(context, sessao_tmp, pasta_base):
    _baixar(context, sessao_tmp, pasta_base, qtd=1)
    sei = SeiSimulado(PROCESSO, falhas_salvar={3: 99})   # a PP não grava de jeito nenhum
    sei.instalar(context)

    with pytest.raises(SystemExit):
        sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, pasta_base=pasta_base)
    assert len(sei.documentos) == 3

    sei.falhas_salvar.clear()                 # a internet voltou
    for pagina in list(context.pages):
        if "editor_montar" in pagina.url:
            pagina.close()
    sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, pasta_base=pasta_base)

    assert [d["tipo"] for d in sei.documentos] == [
        "Despesa Certificada", "NL - Nota de Lançamento", "PP - Preparação de Pagamento",
        "OB - Ordem Bancária de Regularização",
    ]
    assert SeiSimulado.qtd_imagens(sei.documentos[2]) == 1   # a PP reaberta e completada


def test_documento_grande_vai_em_partes(context, sessao_tmp, pasta_base, monkeypatch):
    lancamentos = _baixar(context, sessao_tmp, pasta_base, qtd=1)
    # Troca a OB baixada por 6 páginas "pesadas" (ruído não comprime).
    pasta = os.path.join(pasta_base, elb.nome_pasta_valido(PROCESSO))
    paginas = [_jpg(os.path.join(pasta, f"Ordem Bancária - OB 2026OB136475_{i}.jpg"), 900, 1200, ruido=True)
               for i in range(1, 7)]
    lancamentos[0]["arquivos_ob"] = paginas
    sessao = json.loads(sessao_tmp.read_text(encoding="utf-8"))
    sessao["lancamentos"] = lancamentos
    sessao["grupos_ob"] = [["2026OB136475", paginas]]
    sessao_tmp.write_text(json.dumps(sessao, ensure_ascii=False), encoding="utf-8")

    preparados = [sei2._preparar_imagem_para_insercao(c) for c in paginas]
    total = sum(sei2._tamanho_estimado_imagem(c) for c in preparados)
    limite = total // 2 + sei2.FOLGA_HTML_DOCUMENTO_BYTES + 50_000
    monkeypatch.setattr(sei2, "LIMITE_DOCUMENTO_BYTES", limite)

    sei = SeiSimulado(PROCESSO, limite_bytes=limite)
    sei.instalar(context)
    avisos = []
    sei2.executar_sei2(context, PROCESSO, conferir_no_fim=False, avisos_saida=avisos, pasta_base=pasta_base)

    obs = [d for d in sei.documentos if d["tipo"].startswith("OB")]
    assert len(obs) == 2
    assert sum(SeiSimulado.qtd_imagens(d) for d in obs) == 6
    assert any("dividida em 2 documentos" in aviso for aviso in avisos)
