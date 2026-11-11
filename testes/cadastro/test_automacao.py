"""Testes de ponta a ponta contra o SIGEF simulado (modo lote e modo planilha)."""

import pytest

from excel_falso import Aba, Excel, Pasta
from automacoes.cadastro.automacao import CONFIRMAR_DOMICILIO, INCLUIR_CREDOR
from automacoes.cadastro.fluxos import Relator, executar_lotes, executar_planilha
from automacoes.cadastro.modelos import Lote, Resposta, lote_de_linha
from automacoes.cadastro.navegador import ErroNavegador
from automacoes.cadastro.planilha import Planilha


class RelatorTeste(Relator):
    def __init__(self, corrigir_com=None, cancelar_apos=None):
        self.eventos, self.resultados, self.avisos = [], {}, []
        self.corrigir_com = corrigir_com
        self.cancelar_apos = cancelar_apos

    def inicio(self, chave, lote, atual, total):
        self.eventos.append(("inicio", chave, atual, total))

    def resultado(self, chave, lote, status, texto):
        self.resultados[chave] = (status, texto)

    def aviso(self, texto):
        self.avisos.append(texto)

    def corrigir(self, lote):
        if not self.corrigir_com:
            return False

        for campo, valor in self.corrigir_com.items():
            setattr(lote, campo, valor)

        self.corrigir_com = None
        return True

    def cancelado(self):
        return self.cancelar_apos is not None and len(self.resultados) >= self.cancelar_apos


def test_login_confirmado(navegador):
    assert navegador.logado()


def test_lote_novo_repetido_e_invalido(navegador, servidor):
    lotes = [
        Lote("52998224725", "MARIA DA SILVA", "001", "1234", "56789"),
        Lote("52998224725", "MARIA DA SILVA", "001", "1234", "56789"),  # mesmo domicílio
        Lote("52998224725", "MARIA DA SILVA", "104", "0001", "999"),    # credor já existe
        Lote("00000000000", "CPF RECUSADO", "001", "1", "2"),
    ]
    relator = RelatorTeste()
    resumo = executar_lotes(navegador, lotes, relator)

    assert relator.resultados[1] == ("OK", "Operação realizada com sucesso.")
    assert relator.resultados[2][0] == "JA", relator.resultados
    assert relator.resultados[2][1].startswith("JÁ CADASTRADO: Domicílio Bancário")
    assert relator.resultados[3] == ("OK", "Operação realizada com sucesso.")
    assert relator.resultados[4][0] == "ERRO"
    assert resumo.contagem == {"OK": 2, "JA": 1, "ERRO": 1, "PULADO": 0}

    assert servidor.estado.credores["52998224725"] == "MARIA DA SILVA"
    assert ("52998224725", "104", "0001", "999") in servidor.estado.domicilios

    # Só a aba principal sobra aberta entre os lotes
    assert len(navegador.context.pages) == 1


def test_agencia_e_conta_chegam_ao_sigef_como_escritas(navegador, servidor):
    lote = lote_de_linha("123.456.789-09,JOSE COM DIGITO,001,1234-X,56.789-P")
    relator = RelatorTeste()

    executar_lotes(navegador, [lote], relator)

    assert relator.resultados[1][0] == "OK", relator.resultados
    assert ("12345678909", "001", "1234-X", "56.789-P") in servidor.estado.domicilios


def test_refazer_so_os_lotes_com_erro(navegador, servidor):
    lotes = [
        Lote("52998224725", "MARIA DA SILVA", "001", "1234", "56789"),
        Lote("00000000000", "CPF RECUSADO", "001", "1", "2-3"),
    ]
    resumo = executar_lotes(navegador, lotes, RelatorTeste())

    assert resumo.falhas == [(2, lotes[1])]  # guardado na memória para refazer

    lotes[1].cpf = "45317828791"  # corrigido antes de refazer
    numeros, refazer = zip(*resumo.falhas)
    relator = RelatorTeste()
    novo = executar_lotes(navegador, refazer, relator, numeros=numeros)

    assert relator.eventos == [("inicio", 2, 1, 1)]  # mantém o nº original
    assert relator.resultados[2][0] == "OK", relator.resultados
    assert novo.falhas == []
    assert ("45317828791", "001", "1", "2-3") in servidor.estado.domicilios


def test_confirmacao_manual(navegador, servidor):
    perguntas = []

    def perguntar(lote, acao, editavel):
        perguntas.append((lote.cpf, acao, editavel))

        if lote.cpf == "11144477735":
            return Resposta.PULAR

        if lote.cpf == "39053344705" and lote.banco == "999":
            return Resposta.CORRIGIR

        return Resposta.SIM_TODOS

    lotes = [
        Lote("11144477735", "PULAR ESTE", "001", "1", "1"),
        Lote("39053344705", "CORRIGIR ESTE", "999", "2", "2"),
    ]
    relator = RelatorTeste(corrigir_com={"banco": "237"})
    resumo = executar_lotes(navegador, lotes, relator, perguntar)

    assert relator.resultados[1] == ("PULADO", "PULADO pelo usuário")
    assert relator.resultados[2] == ("OK", "Operação realizada com sucesso.")
    assert "11144477735" not in servidor.estado.credores
    assert ("39053344705", "237", "2", "2") in servidor.estado.domicilios

    # Corrigido: o lote recomeça e "T" libera as demais perguntas do lote
    assert perguntas == [
        ("11144477735", INCLUIR_CREDOR, True),
        ("39053344705", INCLUIR_CREDOR, True),
        ("39053344705", INCLUIR_CREDOR, True),
    ]
    assert resumo.contagem["PULADO"] == 1


def test_parar_no_meio(navegador):
    lotes = [Lote(f"0000000000{n}", f"P{n}", "001", "1", "1") for n in range(1, 4)]
    relator = RelatorTeste(cancelar_apos=1)
    executar_lotes(navegador, lotes, relator)
    assert list(relator.resultados) == [1]


def test_modo_planilha(navegador, servidor):
    aba = Aba("Folha", [
        ["RELAÇÃO DE SERVIDORES"],
        [],
        ["Nº", "ESCOLA", "MUNICÍPIO", "SERVIDOR", "CPF", "BANCO", "AGÊNCIA", "C/C"],
        [1, "EEEF A", "Porto Velho", "JOSÉ SOUZA", 86288366757.0, "Banco do Brasil", 3456, "77-1"],
        [2, "EEEF B", "Ji-Paraná", "ANA LIMA", "123", "Itaú", "1", "2"],
        [],
        [3, "EEEF C", "Ariquemes", "SEM BANCO", "71428793860", "Banco Imaginário", "1", "2"],
        [4, "EEEF D", "Cacoal", "FALTA CONTA", "71428793860", "Caixa", "1", ""],
        [5, "EEEF E", "Vilhena", "JOSÉ SOUZA", "86288366757", "001", "3456", "77-1"],
    ])
    servidor.estado.cpfs_invalidos.add("00000000123")
    pasta = Pasta("servidores.xlsx", [aba])
    planilha = Planilha.da_pasta(Excel(pasta).Workbooks(1), "Folha")

    colunas, primeira, detectou = planilha.colunas_sugeridas()
    assert detectou and primeira == 4
    assert colunas == {"nome": 4, "cpf": 5, "banco": 6, "agencia": 7, "conta": 8}

    final = planilha.ultima_linha(colunas)
    assert final == 9

    relator = RelatorTeste()
    resumo = executar_planilha(navegador, planilha, colunas, range(primeira, final + 1), "J",
                               relator)

    assert aba.valor("J4") == "Operação realizada com sucesso."
    assert aba.valor("J5").startswith("ERRO:")          # CPF 00000000123 recusado
    assert aba.valor("J6") is None                      # linha vazia é ignorada
    assert aba.valor("J7") == "ERRO: banco não reconhecido - Banco Imaginário"
    assert aba.valor("J8") == "ERRO: campos vazios - Conta"
    assert aba.valor("J9").startswith("JÁ CADASTRADO:")
    assert resumo.contagem == {"OK": 1, "JA": 1, "ERRO": 3, "PULADO": 0}
    assert pasta.salvamentos == 5
    assert ("86288366757", "001", "3456", "77-1") in servidor.estado.domicilios


def test_planilha_refaz_so_as_linhas_com_erro(navegador, servidor):
    aba = Aba("Folha", [
        ["CPF", "SERVIDOR", "BANCO", "AGÊNCIA", "C/C"],
        ["15350946056", "ANA REFAZ", "001", "10", "20"],
        ["15350946056", "ANA REFAZ", "104", "10", ""],
    ])
    planilha = Planilha.da_pasta(Excel(Pasta("r.xlsx", [aba])).Workbooks(1), "Folha")
    colunas, primeira, _ = planilha.colunas_sugeridas()

    resumo = executar_planilha(navegador, planilha, colunas, range(primeira, 4), "J",
                               RelatorTeste())
    assert [linha for linha, _ in resumo.falhas] == [3]

    aba.dados[(3, 5)] = "0021-X"  # a pessoa completa a planilha
    relator = RelatorTeste()
    novo = executar_planilha(navegador, planilha, colunas, [3], "J", relator)

    assert list(relator.resultados) == [3] and novo.falhas == []
    assert aba.valor("J3") == "Operação realizada com sucesso."
    assert aba.valor("J2") == "Operação realizada com sucesso."  # não foi refeita
    assert ("15350946056", "104", "10", "0021-X") in servidor.estado.domicilios


def test_planilha_le_digito_da_agencia_e_da_conta():
    aba = Aba("Folha", [
        ["CPF", "SERVIDOR", "BANCO", "AGÊNCIA", "C/C"],
        ["52998224725", "MARIA", "Banco do Brasil", "1234-X", "56789-x"],
    ])
    planilha = Planilha.da_pasta(Excel(Pasta("x.xlsx", [aba])).Workbooks(1), "Folha")
    colunas, _, _ = planilha.colunas_sugeridas()

    lote, _ = planilha.ler_lote(2, colunas)

    assert (lote.agencia, lote.conta) == ("1234-X", "56789-X")


def test_coluna_oculta_gera_aviso(navegador):
    aba = Aba("A", [["SERVIDOR", "CPF", "BANCO", "AGÊNCIA", "CONTA"],
                    ["X", "", "", "", ""], ["Y", "1", "", "", ""]])
    aba.colunas_ocultas.add(10)
    planilha = Planilha(Pasta("p.xlsx", [aba]), aba)
    colunas, primeira, _ = planilha.colunas_sugeridas()
    relator = RelatorTeste()
    executar_planilha(navegador, planilha, colunas, range(primeira, 4), "J", relator)
    assert any("oculta" in aviso for aviso in relator.avisos)


def test_navegador_fechado_interrompe(navegador):
    navegador.page.close()

    with pytest.raises(ErroNavegador):
        executar_lotes(navegador, [Lote("52998224725", "X", "001", "1", "1")], RelatorTeste())

    # Ao abrir de novo, o programa recupera uma aba do SIGEF
    navegador.abrir()
    assert navegador.conectado


def test_acoes_conferidas_no_domicilio(navegador):
    """Credor já existente: só a confirmação do domicílio é perguntada."""
    acoes = []

    def perguntar(lote, acao, editavel):
        acoes.append(acao)
        return Resposta.SIM

    relator = RelatorTeste()
    executar_lotes(navegador, [Lote("52998224725", "MARIA DA SILVA", "341", "9", "9")],
                   relator, perguntar)
    assert relator.resultados[1][0] == "OK", relator.resultados
    assert acoes == [CONFIRMAR_DOMICILIO]
