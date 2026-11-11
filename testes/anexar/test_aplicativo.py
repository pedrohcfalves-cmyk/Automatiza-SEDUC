"""
Testes do núcleo do aplicativo (nucleo.py), do executor (executor.py) e dos dados
dos relatórios (metricas.py). Não usam SEI, SIGEF nem navegador: a
automação é trocada pelo modo treino (anexar/automacao/modo_treino.py).
As respostas são o botão clicado e o que foi preenchido.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from automacoes.anexar import caminhos
from automacoes.anexar.aplicativo import metricas

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # a pasta da Central
PASTA_TESTES = os.path.dirname(os.path.abspath(__file__))


class RelogioFalso:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def andar(self, segundos):
        self.agora += segundos


# ============================================================ metricas


def test_medidor_separa_maquina_e_atencao_humana(tmp_path):
    relogio = RelogioFalso()
    medidor = metricas.Medidor(relogio=relogio, pasta=str(tmp_path))
    medidor.inicio_ciclo()
    relogio.andar(10)                 # SEI1: 10 s de máquina
    medidor.antes_da_pergunta()
    relogio.andar(20)                 # ... e 20 s esperando a pessoa
    medidor.depois_da_pergunta()
    medidor.inicio_etapa("CE")
    relogio.andar(30)
    medidor.inicio_etapa("NL")
    medidor.registrar_erro("A OB não foi feita")
    relogio.andar(5)
    sessao = {
        "processo": "0029.002180/2026-93", "ce": "018705", "valor_total_padronizado": "20000",
        "lancamentos": [
            {"nl": "1", "pp": "P1", "ob": "OB1", "anexo_baixado": True},
            {"nl": "2", "pp": "P2", "ob": "OB1", "anexo_baixado": True},
        ],
    }
    registro = medidor.fim_ciclo("ok", sessao)

    assert registro["duracao_s"] == 65
    assert registro["humano_s"] == 20
    assert registro["maquina_s"] == 45
    assert registro["respostas"] == 1
    assert registro["situacao"] == "concluido"
    assert registro["valor_total_centavos"] == 20000
    assert registro["documentos"] == {"ce": 1, "nl": 2, "pp": 2, "ob": 1, "baixados": 2}
    assert registro["novos"] == {"ce": 1, "nl": 2, "pp": 2, "ob": 1}
    etapas = {etapa["chave"]: etapa for etapa in registro["etapas"]}
    assert etapas["SEI1"]["duracao_s"] == 30 and etapas["SEI1"]["humano_s"] == 20
    assert etapas["CE"]["duracao_s"] == 30 and etapas["CE"]["maquina_s"] == 30
    assert registro["erros"] == [{"etapa": "NL", "titulo": "A OB não foi feita"}]
    assert metricas.ler_execucoes(str(tmp_path)) == [registro]


def test_retomada_conta_so_o_que_foi_feito_agora():
    antes = [{"nl": "1", "pp": "P1"}, {"nl": "2"}]
    depois = [{"nl": "1", "pp": "P1", "ob": "OB9"}, {"nl": "2", "pp": "P2", "ob": "OB9"}]
    assert metricas.contar_novos(antes, depois, ce_reaproveitada=True) == {"ce": 0, "nl": 0, "pp": 1, "ob": 1}
    # CE nova: tudo foi refeito.
    assert metricas.contar_novos(antes, depois, ce_reaproveitada=False) == {"ce": 1, "nl": 2, "pp": 2, "ob": 1}


@pytest.mark.parametrize("status, lancamentos, esperado", [
    ("ok", [{"ob": "1", "anexo_baixado": True}], "concluido"),
    ("ok", [{"ob": None, "anexo_baixado": False}], "pendente"),
    ("ok", [], "pendente"),
    ("erro", [{"ob": "1", "anexo_baixado": True}], "erro"),
    ("interrompido", [], "interrompido"),
])
def test_situacao_final(status, lancamentos, esperado):
    assert metricas.situacao_final(status, {"lancamentos": lancamentos}) == esperado


def test_estimativas_ficam_no_codigo_e_sao_validadas(tmp_path):
    caminho = str(tmp_path / "estimativas_manuais.py")
    assert metricas.ler_estimativas(caminho) == metricas.ESTIMATIVAS_PADRAO  # sem arquivo: padrão
    gravado = metricas.salvar_estimativas({"CE": "2,5", "OB": 6, "inventado": 9}, caminho)
    assert gravado["CE"] == 2.5 and gravado["OB"] == 6.0 and "inventado" not in gravado
    texto = (tmp_path / "estimativas_manuais.py").read_text(encoding="utf-8")
    assert "ESTIMATIVAS_MINUTOS = {" in texto and '"CE": 2.5' in texto
    compile(texto, caminho, "exec")  # continua sendo Python válido
    assert metricas.ler_estimativas(caminho)["CE"] == 2.5
    for ruim in ({"CE": "abc"}, {"NL": -1}, {"PP": 999}):
        with pytest.raises(ValueError):
            metricas.salvar_estimativas(ruim, caminho)
    assert metricas.ler_estimativas(caminho)["CE"] == 2.5  # erro não estraga o que estava salvo


def test_arquivo_de_estimativas_do_programa_e_valido():
    valores = metricas.ler_estimativas()
    assert set(valores) == set(metricas.ESTIMATIVAS_PADRAO)
    assert {c["chave"] for c in metricas.CATEGORIAS} == set(metricas.ESTIMATIVAS_PADRAO)


def test_linha_quebrada_no_historico_nao_derruba_a_leitura(tmp_path):
    (tmp_path / metricas.ARQUIVO_EXECUCOES).write_text('{"id": "a"}\n{quebrada\n{"id": "b"}\n', encoding="utf-8")
    assert [r["id"] for r in metricas.ler_execucoes(str(tmp_path))] == ["a", "b"]


# ============================================================ executor (processo de verdade)


def _ambiente(tmp_path, **extras):
    ambiente = dict(os.environ)
    ambiente.update(
        ANEXAR_MODULO_PRINCIPAL="automacoes.anexar.automacao.modo_treino",
        ANEXAR_SESSAO_SIMULADA=str(tmp_path / "sessao.json"),
        ANEXAR_PASTA_DADOS=str(tmp_path / "dados"),
        ANEXAR_PASTA_RELATORIOS=str(tmp_path / "relatorios"),
        ANEXAR_DEMO_PAUSA="0.01",
        PYTHONPATH=RAIZ,
        PYTHONIOENCODING="utf-8",
    )
    ambiente.update(extras)
    return ambiente


DADOS_FORMULARIO = {
    "cnpj_cpf": "03.508.155/0001-21", "municipio": "Porto Velho", "escola": "ESCOLA DE TREINO", "conta_pp": "105805",
    "conta_ob": "105805", "parcela": "7", "mes_referencia": "10", "programa": "PROAFI", "valor_total": "300,00",
}
# Os cliques de um processo inteiro: entrar (Continuar), número do processo, a TABELA dos
# dados (tudo de uma vez, com 2 lançamentos), Começar, "Terminei no SEI", Terminar por hoje.
RESPOSTAS = [
    "continuar",
    {"botao": "enviar", "valores": {"texto": "0029.002180/2026-93"}},
    {"botao": "conferir", "valores": DADOS_FORMULARIO,
     "lancamentos": [{"valor": "100,00", "nota_de_empenho": "540"}, {"valor": "200,00", "nota_de_empenho": "541"}]},
    "seguir",
    "continuar",
    "nao",
]
CICLO = ["formulario", "formulario", "conferencia", "botoes"]   # perguntas dentro do processo (para o relatório)


def _rodar_executor(tmp_path, respostas, **extras):
    entrada = "".join(json.dumps(resposta, ensure_ascii=False) + "\n" for resposta in respostas)
    resultado = subprocess.run(
        [sys.executable, "-u", "-m", "automacoes.anexar.aplicativo.executor", "automacao"], cwd=RAIZ,
        input=entrada.encode("utf-8"), capture_output=True, timeout=60, env=_ambiente(tmp_path, **extras),
    )
    saida = resultado.stdout.decode("utf-8")
    eventos = [json.loads(linha[1:]) for linha in saida.split("\n") if linha.startswith("\x1e")]
    return resultado.returncode, saida, eventos


def test_executor_emite_etapas_perguntas_e_grava_o_relatorio(tmp_path):
    codigo, saida, eventos = _rodar_executor(tmp_path, RESPOSTAS)
    assert codigo == 0, saida
    tipos = [evento["tipo"] for evento in eventos]
    assert tipos[0] == "inicio" and tipos[-1] == "fim"
    etapas = [evento["chave"] for evento in eventos if evento["tipo"] == "etapa"]
    assert etapas == ["LOGIN", "SEI1", "CE", "NL", "PP", "OB", "BAIXAR", "SEI"]
    pedidos = [evento["pedido"] for evento in eventos if evento["tipo"] == "pergunta"]
    assert [p["tipo"] for p in pedidos] == ["botoes", *CICLO, "botoes"]
    assert tipos.count("respondido") == len(pedidos)
    # A tabela dos dados vem inteira, de uma vez (não um campo por pergunta).
    assert len(pedidos[2]["campos"]) == 9 and pedidos[2]["lancamentos"]["maximo"] == 20
    # Nenhuma pergunta pede para digitar letra: são sempre botões.
    assert all(p["botoes"] for p in pedidos)
    # Ao vivo: o que está sendo feito e as NL/PP/OB que vão saindo.
    andamentos = [evento["texto"] for evento in eventos if evento["tipo"] == "andamento"]
    assert any("Fazendo a NL do valor R$ 200,00" in texto for texto in andamentos)
    ultima_sessao = [evento["sessao"] for evento in eventos if evento["tipo"] == "sessao"][-1]
    assert [item["nl"] for item in ultima_sessao["lancamentos"]] == ["066201", "066202"]
    resumo = next(evento["resumo"] for evento in eventos if evento["tipo"] == "resumo")
    assert resumo["tudo_pronto"] is True and pedidos[-1]["resumo"] == resumo
    fim_ciclo = next(evento for evento in eventos if evento["tipo"] == "ciclo_fim")
    assert fim_ciclo["registro"]["situacao"] == "concluido"
    assert "0029.002180/2026-93" in saida  # a resposta fica no registro técnico

    registros = metricas.ler_execucoes(str(tmp_path / "relatorios"))
    assert len(registros) == 1
    registro = registros[0]
    assert registro["processo"] == "0029.002180/2026-93"
    assert registro["respostas"] == len(CICLO)    # entrar e "outro processo?" ficam fora do ciclo
    assert [etapa["chave"] for etapa in registro["etapas"]] == ["SEI1", "CE", "NL", "PP", "OB", "BAIXAR", "SEI"]
    assert registro["documentos"]["nl"] == 2 and registro["documentos"]["ob"] == 1


def test_executor_registra_erro_e_pendencia(tmp_path):
    codigo, _saida, eventos = _rodar_executor(tmp_path, RESPOSTAS, ANEXAR_DEMO_FALHA_OB="1")
    assert codigo == 0
    assert any(evento["tipo"] == "erro" and evento["titulo"] == "A OB não foi feita" for evento in eventos)
    registro = metricas.ler_execucoes(str(tmp_path / "relatorios"))[0]
    assert registro["situacao"] == "pendente"
    assert registro["erros"][0]["etapa"] == "OB"


def test_executor_parar_no_meio_de_uma_pergunta(tmp_path):
    processo = subprocess.Popen(
        [sys.executable, "-u", "-m", "automacoes.anexar.aplicativo.executor", "automacao"], cwd=RAIZ,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=_ambiente(tmp_path),
    )
    perguntas = 0
    saida = b""
    for linha in processo.stdout:
        saida += linha
        if b'"tipo": "pergunta"' in linha:
            perguntas += 1
            # 1a pergunta (entrar no SEI/SIGEF): Continuar. 2a (número do processo): Parar.
            processo.stdin.write(b'"continuar"\n' if perguntas == 1 else b"\x1ePARAR\n")
            processo.stdin.flush()
    processo.wait(timeout=30)
    assert processo.returncode == 0  # o main.py trata o Ctrl+C sozinho e termina normalmente
    assert "PROGRAMA PARADO" in saida.decode("utf-8")
    registro = metricas.ler_execucoes(str(tmp_path / "relatorios"))[0]
    assert registro["situacao"] == "interrompido"


# ============================================================ núcleo do aplicativo (o que a janela usa)


@pytest.fixture
def nucleo(tmp_path, monkeypatch):
    """Uma Execucao de verdade, rodando o modo treino num processo separado (como a janela faz)."""
    for chave, valor in _ambiente(tmp_path).items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.setattr(metricas, "PASTA_RELATORIOS", str(tmp_path / "relatorios"))
    from automacoes.anexar.aplicativo import nucleo as modulo

    execucao = modulo.Execucao()
    yield modulo, execucao
    execucao.parar()
    if execucao.processo is not None:
        try:
            execucao.processo.wait(timeout=20)
        except subprocess.TimeoutExpired:
            execucao.processo.kill()


def _esperar_pergunta(execucao, tempo=20):
    limite = time.time() + tempo
    while time.time() < limite:
        estado = execucao.estado()
        if estado["pergunta"] is not None:
            return estado
        time.sleep(0.05)
    raise AssertionError("O programa não fez a pergunta a tempo.")


def test_fluxo_completo_pelo_nucleo(nucleo):
    modulo, execucao = nucleo
    execucao.iniciar("automacao", treino=True)
    assert execucao.estado()["treino"] is True
    with pytest.raises(RuntimeError):
        execucao.iniciar("automacao")  # já está rodando
    for resposta in RESPOSTAS:
        estado = _esperar_pergunta(execucao)
        execucao.responder(resposta, estado["pergunta"]["id"])
    limite = time.time() + 20
    while execucao.rodando and time.time() < limite:
        time.sleep(0.05)
    itens = execucao.itens_desde(0)
    texto = "".join(item["texto"] for item in itens if item["tipo"] == "texto")
    assert "RESUMO" in texto and "\x1e" not in texto
    assert execucao.estado()["ultimo_ciclo"]["situacao"] == "concluido"
    assert len(metricas.ler_execucoes(metricas.PASTA_RELATORIOS)) == 1


def test_resposta_de_clique_duplo_nao_vale_para_a_pergunta_seguinte(nucleo):
    _modulo, execucao = nucleo
    execucao.iniciar("automacao", treino=True)
    estado = _esperar_pergunta(execucao)
    execucao.responder("continuar", estado["pergunta"]["id"])
    seguinte = _esperar_pergunta(execucao)
    assert seguinte["pergunta"]["titulo"] == "Qual é o processo?"
    with pytest.raises(RuntimeError, match="já foi respondida"):   # o 2o clique do "Continuar" chega atrasado
        execucao.responder("continuar", estado["pergunta"]["id"])
    assert execucao.estado()["pergunta"]["id"] == seguinte["pergunta"]["id"]


def test_configuracoes_em_tabelas_pelo_nucleo(nucleo, tmp_path, monkeypatch):
    from automacoes.anexar.automacao import configuracoes

    modulo, execucao = nucleo
    monkeypatch.setattr(configuracoes, "CAMINHO_CONFIG", str(tmp_path / "configuracoes.json"))
    tabelas = modulo.tabelas_de_configuracao(execucao)
    assert [s["chave"] for s in tabelas["secoes"]] == ["global", "ce", "nl", "pp", "ob"] and tabelas["bloqueado"] is False
    salvo = modulo.salvar_configuracao(execucao, "pp", {"agencia": "0001-9"})
    assert {c["chave"]: c["valor"] for c in salvo["campos"]}["agencia"] == "0001-9"
    with pytest.raises(configuracoes.ErroNasConfiguracoes) as erro:
        modulo.salvar_configuracao(execucao, "ob", {"fonte_recurso": "abc"})
    assert "fonte_recurso" in erro.value.erros
    voltou = modulo.salvar_configuracao(execucao, "pp", padrao=True)
    assert voltou["alterados"] == 0
    assert "Todos os direitos reservados" in modulo.ler_licenca()


def test_configuracoes_ficam_travadas_enquanto_a_automacao_trabalha(nucleo):
    modulo, execucao = nucleo
    execucao.iniciar("automacao", treino=True)
    _esperar_pergunta(execucao)                                  # "Entre no SEI e no SIGEF": não é hora de mudar
    assert modulo.tabelas_de_configuracao(execucao)["bloqueado"] is True
    with pytest.raises(RuntimeError, match="trabalhando"):
        modulo.salvar_configuracao(execucao, "pp", {"agencia": "1"})


def test_salvar_estimativas(tmp_path):
    arquivo = str(tmp_path / "estimativas_manuais.py")
    assert metricas.salvar_estimativas({"CE": 7}, arquivo)["CE"] == 7.0
    assert metricas.ler_estimativas(arquivo)["CE"] == 7.0
    with pytest.raises(Exception):
        metricas.salvar_estimativas({"CE": "muito"}, arquivo)


# ============================================================ pasta dados/


def test_dados_das_versoes_antigas_vao_para_a_pasta_dados(tmp_path):
    (tmp_path / "sessao_atual.json").write_text("{}", encoding="utf-8")
    (tmp_path / "relatorios").mkdir()
    (tmp_path / "relatorios" / "execucoes.jsonl").write_text("{}\n", encoding="utf-8")
    novo = tmp_path / "dados"
    destinos = {"sessao_atual.json": str(novo / "sessao_atual.json"), "relatorios": str(novo / "relatorios"),
                "configuracoes_automacao.json": str(novo / "configuracoes_automacao.json")}
    assert sorted(caminhos.migrar_dados_antigos(str(tmp_path), destinos)) == ["relatorios", "sessao_atual.json"]
    assert (novo / "relatorios" / "execucoes.jsonl").is_file() and not (tmp_path / "sessao_atual.json").exists()
    # Já existe no lugar novo: o antigo fica onde está (nada é sobrescrito).
    (tmp_path / "sessao_atual.json").write_text('{"velho": 1}', encoding="utf-8")
    assert caminhos.migrar_dados_antigos(str(tmp_path), destinos) == []
    assert (novo / "sessao_atual.json").read_text(encoding="utf-8") == "{}"


def test_diagnostico_do_computador_lista_as_bibliotecas():
    from automacoes.anexar.sistema import ambiente

    info = ambiente.diagnostico()
    # Na Central a janela é a dela (pywebview), não mais a do PySide6.
    assert set(info["bibliotecas"]) == {"playwright", "pymupdf", "pillow", "pywebview"}
    assert info["pasta_programa"] and isinstance(info["problemas"], list)
