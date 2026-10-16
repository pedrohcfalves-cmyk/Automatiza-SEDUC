"""
Modo planilha (parte interativa): escolher a planilha e a aba, indicar quais colunas
alimentam cada campo, escolher a linha inicial/final e ler os lançamentos.

  obter_lotes()         -> conduz tudo, usando o Excel (pywin32); devolve os lotes lidos
  configurar_e_ler()    -> a parte que não depende do Excel (recebe uma tabela já aberta)
"""

import logging
import os

from . import config, excel_com, menu, planilha
from .modelos import DadosDare
from .planilha import CAMPOS, OBRIGATORIOS, ROTULOS, Mapeamento, Origem

log = logging.getLogger("dare.fluxo_planilha")

MAX_COLUNAS_EXIBIDAS = 26
MAX_PROBLEMAS_EXIBIDOS = 15


# ---- Escolha da planilha e da aba ---------------------------------------------------------

def _cabecalho_tela(titulo: str, linhas: list[str]) -> None:
    menu.limpar()
    menu.banner()
    print()
    menu.caixa(titulo, linhas)
    print()


def _abrir_arquivo_no_windows(caminho) -> None:
    try:
        os.startfile(str(caminho))  # type: ignore[attr-defined]  # só existe no Windows
    except Exception:  # noqa: BLE001
        menu.aviso(f"Abra o arquivo manualmente: {caminho}")


def _criar_modelo() -> None:
    destino = config.PASTA_MODELOS / "modelo_dare.xlsx"
    if destino.exists() and not menu.sim_nao(
        f"Já existe um modelo em {destino.name}. Criar de novo (substitui o arquivo)?", padrao=False
    ):
        _abrir_arquivo_no_windows(destino)
        return
    try:
        excel_com.criar_modelo(destino)
    except excel_com.ExcelIndisponivel as exc:
        menu.erro(str(exc))
        return
    menu.sucesso(f"Modelo criado: {destino}")
    _abrir_arquivo_no_windows(destino)
    menu.info("Preencha a planilha, salve e volte aqui. Ela aparecerá na lista de abertas.")
    menu.pausar("Pressione Enter para atualizar a lista...")


def _escolher_pasta():
    """Lista as planilhas abertas no Excel (ou pede o caminho). Devolve PastaAberta ou None."""
    while True:
        try:
            abertas = excel_com.listar_abertas()
        except excel_com.ExcelIndisponivel as exc:
            _cabecalho_tela("Modo planilha", ["Não foi possível usar o Excel."])
            menu.erro(str(exc))
            menu.pausar()
            return None
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao listar as planilhas abertas")
            menu.aviso(f"Não consegui listar as planilhas abertas ({exc}).")
            abertas = []

        linhas = ["Escolha a planilha com os dados dos DAREs."]
        if abertas:
            linhas.append("Planilhas abertas no Excel agora:")
            linhas += [f"  {i}  {p.nome}   ({p.caminho})" for i, p in enumerate(abertas, 1)]
        else:
            linhas.append("Nenhuma planilha aberta no Excel foi encontrada.")
        linhas += [
            "",
            "C  digitar o caminho do arquivo     M  criar a planilha modelo",
            "R  atualizar a lista                0  voltar",
            "Planilha em 'Modo de Exibição Protegido' não aparece: clique em Habilitar edição.",
        ]
        _cabecalho_tela("Modo planilha — escolha a planilha", linhas)

        resposta = menu.entrada("Número da planilha, C, M, R ou 0").lower()
        if resposta in ("0", "v", "voltar"):
            return None
        if resposta in ("", "r"):
            continue
        if resposta == "m":
            _criar_modelo()
            continue
        if resposta == "c":
            caminho = menu.entrada("Caminho completo do arquivo (.xlsx, .xlsm, .xls)")
            if not caminho:
                continue
            try:
                return excel_com.abrir_por_caminho(caminho)
            except (FileNotFoundError, excel_com.ExcelIndisponivel) as exc:
                menu.erro(str(exc))
                menu.pausar()
                continue
        if resposta.isdigit() and 1 <= int(resposta) <= len(abertas):
            return abertas[int(resposta) - 1]
        menu.erro("Opção inválida.")
        menu.pausar()


def _escolher_aba(pasta) -> str | None:
    abas = pasta.abas()
    if not abas:
        menu.erro("Essa planilha não tem abas de dados.")
        menu.pausar()
        return None
    if len(abas) == 1:
        menu.info(f"A planilha tem uma única aba: '{abas[0]}'.")
        return abas[0]
    _cabecalho_tela(
        f"Escolha a aba — {pasta.nome}",
        ["Digite o número ou o nome da aba:"] + [f"  {i}  {nome}" for i, nome in enumerate(abas, 1)],
    )
    while True:
        resposta = menu.entrada("Aba", f"Enter = {abas[0]}  ·  0 = voltar")
        if resposta == "0":
            return None
        if not resposta:
            return abas[0]
        if resposta.isdigit() and 1 <= int(resposta) <= len(abas):
            return abas[int(resposta) - 1]
        achada = [a for a in abas if a.strip().lower() == resposta.lower()]
        if achada:
            return achada[0]
        menu.erro("Aba não encontrada. Digite o número ou o nome exato.")


# ---- Mapeamento de colunas ----------------------------------------------------------------

def descrever_origem(origem: Origem, cabecalhos: dict[int, str]) -> str:
    if origem.fixo is not None:
        return f"valor fixo '{origem.fixo}' (todas as linhas)"
    if origem.coluna:
        nome = cabecalhos.get(origem.coluna)
        letra = planilha.numero_para_letra(origem.coluna)
        return f"coluna {letra}" + (f" ('{nome}')" if nome else "")
    return "—"


def _mostrar_mapeamento(mapeamento: Mapeamento, cabecalhos: dict[int, str]) -> None:
    campos = []
    for campo in CAMPOS:
        origem = mapeamento.origem(campo)
        if origem.vazia:
            texto = "não informado" if campo in OBRIGATORIOS else f"não informado ({planilha.PADRAO_DESCRICAO[campo]})"
        else:
            texto = descrever_origem(origem, cabecalhos)
        campos.append((ROTULOS[campo], texto))
    cab = f"linha {mapeamento.linha_cabecalho}" if mapeamento.linha_cabecalho else "sem cabeçalho"
    menu.caixa_campos(f"Colunas usadas ({cab})", campos)


def _mostrar_colunas(cabecalhos: dict[int, str]) -> None:
    if not cabecalhos:
        return
    itens = [f"{planilha.numero_para_letra(c)}: {t}" for c, t in sorted(cabecalhos.items())]
    extra = len(itens) - MAX_COLUNAS_EXIBIDAS
    itens = itens[:MAX_COLUNAS_EXIBIDAS] + ([f"... e mais {extra}"] if extra > 0 else [])
    menu.caixa("Colunas encontradas no cabeçalho", ["   ".join(itens)])


def _perguntar_inteiro(rotulo: str, padrao: int, minimo: int = 0) -> int:
    while True:
        resposta = menu.entrada(rotulo, f"Enter = {padrao}")
        if not resposta:
            return padrao
        if resposta.isdigit() and int(resposta) >= minimo:
            return int(resposta)
        menu.erro(f"Digite um número inteiro (mínimo {minimo}).")


def _editar_mapeamento(tabela, atual: Mapeamento) -> Mapeamento:
    """Pergunta, campo a campo, de onde vem cada informação."""
    print()
    menu.info("Para cada campo digite: a LETRA da coluna (ex.: C), o NOME do cabeçalho,")
    menu.info("=valor para usar o mesmo valor em todas as linhas (ex.: =100,00), ou - para nenhum.")
    linha_cab = _perguntar_inteiro(
        "Linha do cabeçalho (0 = a planilha não tem cabeçalho)", atual.linha_cabecalho
    )
    cabecalhos = planilha.ler_cabecalhos(tabela, linha_cab)
    _mostrar_colunas(cabecalhos)
    print()
    campos: dict[str, Origem] = {}
    for campo in CAMPOS:
        obrigatorio = campo in OBRIGATORIOS
        existente = atual.origem(campo)
        if not existente.vazia:
            dica = f"Enter = {descrever_origem(existente, cabecalhos)}"
        else:
            dica = "obrigatório" if obrigatorio else planilha.PADRAO_DESCRICAO[campo]
        while True:
            resposta = menu.entrada(ROTULOS[campo], dica)
            try:
                if not resposta:
                    origem = existente
                else:
                    origem = planilha.interpretar_origem(resposta, cabecalhos)
            except ValueError as exc:
                menu.erro(str(exc))
                continue
            if origem.vazia and obrigatorio:
                menu.erro("Este campo é obrigatório: indique a coluna ou =valor.")
                continue
            break
        if not origem.vazia:
            campos[campo] = origem
    return Mapeamento(campos, linha_cab)


def _obter_mapeamento(tabela, chave: str) -> Mapeamento:
    salvo = planilha.carregar_mapeamento(chave)
    if salvo and not salvo.faltando():
        mapeamento, origem_txt = salvo, "salvo da última vez para esta planilha/aba"
    else:
        linha_cab = planilha.detectar_linha_cabecalho(tabela)
        sugestao = planilha.sugerir_mapeamento(planilha.ler_cabecalhos(tabela, linha_cab))
        mapeamento, origem_txt = Mapeamento(sugestao, linha_cab), "sugerido pelos cabeçalhos"

    while True:
        cabecalhos = planilha.ler_cabecalhos(tabela, mapeamento.linha_cabecalho)
        print()
        if mapeamento.faltando():
            menu.aviso("Não deu para reconhecer todas as colunas sozinho. Vamos indicá-las.")
            mapeamento = _editar_mapeamento(tabela, mapeamento)
            continue
        menu.info(f"Mapeamento {origem_txt}:")
        _mostrar_mapeamento(mapeamento, cabecalhos)
        if menu.sim_nao("Usar estas colunas?", padrao=True):
            planilha.salvar_mapeamento(chave, mapeamento)
            return mapeamento
        mapeamento = _editar_mapeamento(tabela, mapeamento)
        origem_txt = "informado por você"


# ---- Intervalo de linhas e leitura --------------------------------------------------------

def _escolher_intervalo(tabela, mapeamento: Mapeamento) -> tuple[int, int] | None:
    ultima = planilha.ultima_linha_com_dados(tabela, mapeamento)
    primeira_dados = mapeamento.linha_cabecalho + 1 if mapeamento.linha_cabecalho else 1
    if ultima < primeira_dados:
        menu.erro("Não encontrei dados abaixo do cabeçalho nas colunas indicadas.")
        return None
    print()
    menu.info(f"Dados encontrados da linha {primeira_dados} até a linha {ultima}.")
    while True:
        inicial = _perguntar_inteiro("Linha inicial", primeira_dados, minimo=1)
        if inicial > ultima:
            menu.erro(f"A última linha com dados é a {ultima}.")
            continue
        final = _perguntar_inteiro("Linha final (vazio = até a última com dados)", ultima, minimo=1)
        if final < inicial:
            menu.erro("A linha final não pode ser menor que a inicial.")
            continue
        if final > ultima:
            menu.info(f"Não há dados depois da linha {ultima}; vou ler até ela.")
            final = ultima
        if mapeamento.linha_cabecalho and inicial <= mapeamento.linha_cabecalho:
            menu.aviso(f"A linha {mapeamento.linha_cabecalho} é o cabeçalho; ela seria lida como dado.")
            if not menu.sim_nao("Manter esta linha inicial mesmo assim?", padrao=False):
                continue
        return inicial, final


def _mostrar_leitura(resultado: planilha.ResultadoLeitura) -> None:
    linhas = [
        f"Linhas válidas: {len(resultado.lotes)}",
        f"Linhas com problema (ficam de fora): {len(resultado.problemas)}",
        f"Linhas em branco puladas: {resultado.vazias}",
    ]
    if resultado.ocultas:
        linhas.append(f"Linhas ocultas/filtradas puladas: {resultado.ocultas}")
    print()
    menu.caixa("Leitura da planilha", linhas, cor=menu.AMARELO if resultado.problemas else menu.VERDE)
    for p in resultado.problemas[:MAX_PROBLEMAS_EXIBIDOS]:
        menu.erro(f"Linha {p.linha}: {p.mensagem}")
    if len(resultado.problemas) > MAX_PROBLEMAS_EXIBIDOS:
        menu.aviso(f"... e mais {len(resultado.problemas) - MAX_PROBLEMAS_EXIBIDOS} linha(s) com problema (veja o log).")
    for p in resultado.problemas:
        log.warning("Planilha, linha %d ignorada: %s", p.linha, p.mensagem)


def configurar_e_ler(tabela) -> list[DadosDare] | None:
    """
    Dada uma aba já aberta: define as colunas, o intervalo de linhas e lê os lançamentos.
    Devolve a lista (nunca vazia) ou None se não houver nada para processar.
    """
    chave = planilha.chave_mapeamento(tabela.nome, tabela.aba)
    log.info("Modo planilha: %s / aba %s", tabela.nome, tabela.aba)
    mapeamento = _obter_mapeamento(tabela, chave)
    intervalo = _escolher_intervalo(tabela, mapeamento)
    if intervalo is None:
        menu.pausar()
        return None
    inicial, final = intervalo
    resultado = planilha.ler_lotes(tabela, mapeamento, inicial, final)
    log.info(
        "Planilha lida (linhas %d a %d): %d válidas, %d com problema, %d vazias, %d ocultas",
        inicial, final, len(resultado.lotes), len(resultado.problemas), resultado.vazias, resultado.ocultas,
    )
    _mostrar_leitura(resultado)
    if not resultado.lotes:
        menu.erro("Nenhuma linha válida para processar.")
        menu.pausar()
        return None
    if resultado.problemas and not menu.sim_nao(
        f"Continuar só com as {len(resultado.lotes)} linha(s) válida(s)?", padrao=True
    ):
        return None
    return resultado.lotes


def obter_lotes() -> list[DadosDare] | None:
    """Fluxo completo do modo planilha. Devolve os lotes lidos ou None (voltou/cancelou/sem dados)."""
    pasta = _escolher_pasta()
    if pasta is None:
        return None
    try:
        aba = _escolher_aba(pasta)
        if aba is None:
            return None
        return configurar_e_ler(pasta.tabela(aba))
    except ValueError as exc:  # ex.: faltam campos, aba inexistente
        menu.erro(str(exc))
        menu.pausar()
        return None
    except excel_com.ExcelIndisponivel as exc:
        menu.erro(str(exc))
        menu.pausar()
        return None
    except Exception as exc:  # noqa: BLE001 - erro de COM durante a leitura
        log.exception("Falha ao ler a planilha")
        menu.erro(f"Falha ao ler a planilha: {exc}")
        menu.pausar()
        return None
    finally:
        pasta.fechar()
