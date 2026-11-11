"""
Testes da conversa com a pessoa (interacao.py) e da tabela dos dados do
processo (dados_processo.py): tudo por botões e tabelas, nada em branco por
engano, a soma dos lançamentos explicada, e a retomada sem fazer nada em dobro.
"""
import pytest

from automacoes.anexar.automacao import dados_processo, interacao, utils
from automacoes.anexar.automacao import fluxo as main
from automacoes.anexar.automacao.valores import padronizar_valor

DADOS = {
    "cnpj_cpf": "03.508.155/0001-21", "municipio": "Porto Velho", "escola": "EEEF TESTE", "conta_pp": "105805",
    "conta_ob": "105805", "parcela": "7", "mes_referencia": "10", "programa": "PROAFI", "valor_total": "150,00",
}


@pytest.fixture
def tela(monkeypatch):
    """A tela de mentira: responde com os cliques da fila e guarda os pedidos."""
    class Tela:
        def __init__(self):
            self.fila = []
            self.pedidos = []

        def clicar(self, *respostas):
            self.fila.extend(respostas)

        def __call__(self, pedido):
            self.pedidos.append(pedido)
            if not self.fila:
                raise AssertionError(f"o programa pediu mais respostas do que o teste deu: {pedido.get('titulo')!r}")
            return self.fila.pop(0)

    falsa = Tela()
    monkeypatch.setattr(interacao, "_perguntar_pelo_aplicativo", falsa)
    return falsa


def _formulario(lancamentos, **mudancas):
    return {"botao": "conferir", "valores": {**DADOS, **mudancas},
            "lancamentos": [{"valor": v, "nota_de_empenho": ne} for v, ne in lancamentos]}


# ============================================================ botões


def test_confirmar_e_continuar_sao_botoes(tela):
    tela.clicar("sim", "nao", "continuar")
    assert interacao.confirmar("Usar a CE?", sim="Usar", nao="Fazer outra") is True
    assert interacao.confirmar("Usar a CE?") is False
    interacao.continuar("Entre no SEI", passos=["Abra o Chrome", "Entre"], rotulo="Já entrei")
    primeiro, _segundo, terceiro = tela.pedidos
    assert primeiro["tipo"] == "botoes" and [b["rotulo"] for b in primeiro["botoes"]] == ["Usar", "Fazer outra"]
    assert terceiro["passos"] == ["Abra o Chrome", "Entre"] and terceiro["botoes"][0]["rotulo"] == "Já entrei"
    assert len({p["id"] for p in tela.pedidos}) == 3          # cada pergunta tem o seu número


def test_botao_que_nao_existe_ou_desabilitado_pergunta_de_novo(tela):
    tela.clicar("talvez", "b", "a")
    valor = interacao.escolher("Escolha", botoes=[interacao.botao("a", "A"), interacao.botao("b", "B", desabilitado=True)])
    assert valor == "a" and len(tela.pedidos) == 3


def test_texto_nao_aceita_em_branco(tela):
    tela.clicar({"botao": "enviar", "valores": {"texto": "  "}}, {"botao": "enviar", "valores": {"texto": "0029.1/2026"}})
    assert interacao.pedir_texto("Qual é o processo?", "Número", atual="") == "0029.1/2026"
    assert tela.pedidos[1]["erros"] == {"texto": "Este campo não pode ficar em branco."}


def test_perguntar_ou_reusar_vem_preenchido_com_o_salvo(tela):
    tela.clicar({"botao": "enviar", "valores": {"texto": "123"}})
    assert utils.perguntar_ou_reusar("👤 CNPJ", "cnpj", {"cnpj": "123"}) == "123"
    assert tela.pedidos[0]["campos"][0]["valor"] == "123"


def test_avisos_vao_para_o_aplicativo(monkeypatch, capsys):
    recebidos = []
    monkeypatch.setattr(interacao, "_avisar_o_aplicativo", lambda tipo, dados: recebidos.append((tipo, dados)))
    interacao.andamento("Fazendo a NL", 2, 3)
    utils.inicio_de_etapa("PP", "PP -- Preparação de Pagamento", "Faz as PPs.")
    assert recebidos[0] == ("andamento", {"texto": "Fazendo a NL", "atual": 2, "total": 3})
    assert recebidos[1] == ("etapa", {"chave": "PP", "titulo": "PP -- Preparação de Pagamento", "texto": "Faz as PPs."})
    saida = capsys.readouterr().out
    assert "PASSO 3 de 6" in saida and "NÃO mexa no Chrome" in saida and "(2 de 3)" in saida


# ============================================================ a tabela dos dados do processo


def test_tabela_vem_toda_de_uma_vez_e_preenchida(tela):
    tela.clicar(_formulario([("150,00", "540")]), "seguir")
    dados_processo.coletar("0029.1/2026", {**DADOS, "lancamentos": [{"valor": "150,00", "nota_de_empenho": "540"}]})
    formulario = tela.pedidos[0]
    assert formulario["tipo"] == "formulario"
    assert [c["chave"] for c in formulario["campos"]] == [c for c, *_ in dados_processo.CAMPOS]   # TODOS juntos
    campos = {c["chave"]: c for c in formulario["campos"]}
    assert campos["escola"]["valor"] == "EEEF TESTE" and campos["escola"]["anterior"] == "EEEF TESTE"
    assert campos["mes_referencia"]["tipo"] == "mes" and ["13", "13 - Décimo Terceiro"] in campos["mes_referencia"]["opcoes"]
    assert formulario["lancamentos"]["itens"] == [{"valor": "150,00", "nota_de_empenho": "540"}]
    assert formulario["lancamentos"]["maximo"] == 20


def test_erros_voltam_ao_lado_de_cada_campo(tela):
    tela.clicar(_formulario([("abc", ""), ("", "541")], cnpj_cpf="123", mes_referencia="", escola=""),
                _formulario([("150,00", "540")]), "seguir")
    dados = dados_processo.coletar("0029.1/2026", {})
    erros = tela.pedidos[1]["erros"]
    assert set(erros) == {"cnpj_cpf", "mes_referencia", "escola", "lancamentos.0.valor",
                          "lancamentos.0.nota_de_empenho", "lancamentos.1.valor"}
    assert "14 números (CNPJ) ou 11" in erros["cnpj_cpf"]
    assert tela.pedidos[1]["campos"][2]["valor"] == ""          # o que foi digitado volta igual
    assert dados["lancamentos"] == [{"valor": "150,00", "valor_padronizado": "15000", "nota_de_empenho": "540"}]
    assert dados["valor_total_padronizado"] == "15000" and dados["mes_referencia"] == "10"


def test_sem_lancamento_nao_passa(tela):
    tela.clicar(_formulario([("", "")]), _formulario([("150,00", "1")]), "seguir")
    dados_processo.coletar("p", {})
    assert tela.pedidos[1]["erros"] == {"lancamentos": "Coloque pelo menos um lançamento (valor e nota de empenho)."}


class TestSoma:
    def test_falta(self):
        comparacao = dados_processo.comparar_total([{"valor": "2.265,75"}], "5.335,50")
        assert comparacao["tipo"] == "falta" and "Falta lançar R$ 3.069,75" in comparacao["texto"]

    def test_passou(self):
        assert "passou R$ 1,00" in dados_processo.comparar_total([{"valor": "10,00"}], "9,00")["texto"]

    def test_confere(self):
        assert dados_processo.comparar_total([{"valor": "100,00"}, {"valor": "50,00"}], "150,00")["tipo"] == "ok"

    def test_soma_errada_ainda_deixa_seguir_mas_avisa(self, tela):
        tela.clicar(_formulario([("100,00", "1")]), "seguir")
        dados = dados_processo.coletar("p", {})
        conferencia = tela.pedidos[1]
        assert conferencia["tom"] == "atencao" and conferencia["lancamentos"]["comparacao"]["tipo"] == "falta"
        assert conferencia["botoes"][0]["rotulo"] == "A soma não bate — começar mesmo assim"
        assert len(dados["lancamentos"]) == 1


def test_valor_sem_virgula_vira_centavos():
    assert padronizar_valor("1000") == ("1000", "10,00")
    assert padronizar_valor("1.105,50") == ("110550", "1.105,50")
    assert padronizar_valor("1105,5") == ("110550", "1.105,50")


def test_retomada_guarda_nl_pp_ob_de_quem_nao_mudou():
    salvos = [{"valor": "100,00", "valor_padronizado": "10000", "nota_de_empenho": "1", "nl": "N1", "pp": "P1"},
              {"valor": "50,00", "valor_padronizado": "5000", "nota_de_empenho": "2", "nl": "N2"}]
    dados, erros = dados_processo.validar(DADOS, [{"valor": "100,00", "nota_de_empenho": "1"},
                                                  {"valor": "55,00", "nota_de_empenho": "2"}], salvos)
    assert erros == {}
    assert dados["lancamentos"][0]["nl"] == "N1" and dados["lancamentos"][0]["pp"] == "P1"   # igual: guarda
    assert "nl" not in dados["lancamentos"][1]                                                # mudou: faz de novo


# ============================================================ erro inesperado


def test_erro_inesperado_vira_explicacao_e_vai_para_o_arquivo(tmp_path, monkeypatch, capsys):
    arquivo = tmp_path / "registro_de_erros.txt"
    monkeypatch.setattr(utils, "CAMINHO_REGISTRO_ERROS", str(arquivo))
    try:
        raise RuntimeError("SEI fora do ar")
    except RuntimeError as erro:
        main._avisar_erro_inesperado(erro)
    saida = capsys.readouterr().out
    assert "O programa parou" in saida and "SEI fora do ar" in saida and "MESMO processo" in saida
    assert "Traceback" not in saida                       # nada de tela técnica
    assert "python main.py" not in saida                  # e nada de "digitar comando"
    assert "RuntimeError: SEI fora do ar" in arquivo.read_text(encoding="utf-8")


def test_fluxo_nao_pede_para_digitar_letras_nem_apertar_enter():
    """Nenhuma parte da automação manda a pessoa digitar uma letra e apertar ENTER."""
    import pathlib
    import re

    pasta = pathlib.Path(main.__file__).parent
    proibido = re.compile(r"Digite (S|N|a LETRA|a opção|E ou P)|aperte ENTER|Ctrl \+ C", re.IGNORECASE)
    achados = []
    for arquivo in pasta.glob("*.py"):
        if arquivo.name == "interacao.py":
            continue
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
            if proibido.search(linha) and not linha.lstrip().startswith("#") and "nada de digitar" not in linha:
                achados.append(f"{arquivo.name}:{numero}: {linha.strip()}")
    assert achados == []
    for arquivo in pasta.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        if arquivo.name != "interacao.py":
            assert not re.search(r"(?<![\w.])input\(", texto.split('if __name__ == "__main__":')[0]), arquivo.name
