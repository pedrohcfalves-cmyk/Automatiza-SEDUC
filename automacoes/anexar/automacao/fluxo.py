"""
Orquestra o fluxo completo de regularização, na ordem:

    Login (1x) -> SEI(1) -> CE (1x, Valor Total) -> NL (em lote) ->
    PP (em lote) -> OB (1 para o lote todo) -> Anexar Documento (baixa os
    relatórios do SIGEF) -> SEI(2) (anexa tudo de volta no processo)

O ciclo inteiro (executar_ciclo) roda pra UM processo por vez. main()
repete esse ciclo automaticamente pro PRÓXIMO processo -- perguntando,
ao final de cada um, se quer continuar -- até o usuário decidir parar
(clicando em "Terminar por hoje", ou em "Parar o programa").

Antes do primeiro SEI(1), garantir_chrome_pronto() garante que existe um
Chrome de depuração aberto (abrindo um automaticamente se preciso -- ver
conectar_chrome() em utils.py) e preparar_sessao_login() abre as abas do
SEI e do SIGEF (sem nenhuma automação de preenchimento) e pede uma
confirmação de que o usuário já entrou com a própria conta nos dois.
Isso roda só UMA VEZ -- ou de novo, automaticamente, se o Chrome de
depuração tiver sido fechado nesse meio tempo (detectado no início de
cada ciclo novo).

O SEI(1) roda uma vez por processo: abre o processo e coleta os dados
compartilhados (CNPJ/CPF, contas, escola etc.), o Valor Total da
parcela e a lista de lançamentos desse processo -- de 1 a 20 pares de
Valor + Nota de Empenho que somados dão o Valor Total (ver
coletar_lancamentos() em etapa_sei1.py).

A CE é gerada uma única vez, com o Valor Total (é a mesma Despesa
Certificada pra todos os lançamentos). A partir dela, as NLs de todos os
lançamentos são geradas em sequência sem recarregar a página
(executar_nl_lote), e o mesmo vale para as PPs (executar_pp_lote) --
recarregar a página a cada lançamento seria lento e desnecessário, já
que a CE é sempre a mesma. No fim, UMA OB só paga o lote inteiro: na
busca de PPs da OB são marcadas todas as PPs geradas (PP + valor têm que
bater), e todos os lançamentos ficam com o mesmo número de OB.

LOTE = os lançamentos do menu do SEI(1): 1 CE -> N lançamentos, cada um
com 1 NL + 1 PP (todas com a configuração dos submenus da CE, PP e OB)
-> 1 OB. Para configurações diferentes, é outro lote (outro processo).

Com CE + NL + PP + OB de todos os lançamentos prontos, a Etapa Anexar
Documento (etapa_listar_baixar.py) baixa os relatórios de cada um (CE,
OB, NL, PP) direto do SIGEF, já convertidos em JPG, na pasta do
processo (a CE e a OB são as mesmas pra todos os lançamentos, então só
são baixadas uma vez). Por fim, a Etapa SEI (2) (etapa_sei2.py) volta
pro SEI, reabre o processo e inclui esses JPGs como documentos novos
(CE, uma NL + uma PP por lançamento, e a OB), cada um já com Nível de
Acesso (Restrito) e Hipótese Legal (Documento Preparatório) preenchidos.

Se um lançamento não conseguir gerar sua NL/PP/OB (ou baixar/anexar o
relatório), ele fica marcado como pendente no resumo final e o loop
segue pro próximo -- uma falha não derruba os demais.

Toda pergunta à pessoa é feita com BOTÕES (anexar/automacao/interacao.py):
nada de digitar uma letra e apertar ENTER.
"""
from automacoes.anexar.automacao import interacao
from automacoes.anexar.automacao.etapa_sei1 import executar_sei1
from automacoes.anexar.automacao.configuracoes import config_ob, problemas_ob
from automacoes.anexar.automacao.etapa_ce import CEConfiguracaoIncompleta, executar_ce
from automacoes.anexar.automacao.etapa_nl import executar_nl_lote
from automacoes.anexar.automacao.etapa_pp import PPConfiguracaoIncompleta, executar_pp_lote
from automacoes.anexar.automacao.etapa_ob import OBConfiguracaoIncompleta, executar_ob_lote
from automacoes.anexar.automacao.etapa_listar_baixar import executar_anexar_lote
from automacoes.anexar.automacao.etapa_sei2 import executar_sei2
from automacoes.anexar.automacao.utils import (
    URL_SEI,
    URL_SIGEF,
    caixa,
    carregar_sessao,
    conectar_chrome,
    explicar_erro,
    inicio_de_etapa,
    instrucao,
    obter_ou_criar_aba,
    registrar_detalhes_tecnicos,
    salvar_sessao,
)


def obter_ce(context, processo: str, dados_ce: dict) -> tuple[str, bool]:
    """
    Antes de gerar uma CE nova, confere se já existe uma CE salva de uma
    execução anterior (mesmo mecanismo dos outros dados -- ver
    coletar_dados_sigef() em etapa_sei1.py). Se existir, pergunta se
    quer reaproveitá-la em vez de gerar outra -- evita duplicar a CE no
    SIGEF e economiza o tempo de preencher o formulário de novo.

    Responder N (ou não existir nenhuma CE salva) gera uma CE nova
    normalmente.

    Retorna (ce, reaproveitada) -- o chamador usa `reaproveitada` pra
    saber se pode confiar nas NL/PP/OB/anexos já salvos (mesma CE) ou se
    eles pertencem a uma CE antiga e precisam ser refeitos (ver
    executar_ciclo()).
    """
    sessao = carregar_sessao()
    ce_salvo = sessao.get("ce")

    if ce_salvo:
        caixa("📦 JÁ EXISTE UMA CE FEITA ANTES", [f"CE guardada: {ce_salvo}"])
        if interacao.confirmar(
            "Já existe uma CE feita antes",
            [
                f"CE guardada: {ce_salvo}  ·  Valor Total de agora: R$ {dados_ce['valor_total']}",
                "Use a CE guardada se você está CONTINUANDO este mesmo processo (o programa parou no meio).",
                "Faça uma CE nova se é um processo NOVO ou se o valor mudou.",
            ],
            sim=f"Usar a CE guardada ({ce_salvo})",
            nao="Fazer uma CE nova",
            tom="atencao",
        ):
            print(f"➡️  Usando a CE {ce_salvo} que já existia -- seguindo para a NL.")
            return ce_salvo, True
        print("🔄 Certo, o programa vai fazer uma CE nova.")

    # Configuração incompleta (ex: Nota Fiscal sem Série): nada foi
    # preenchido no SIGEF ainda -- em vez de derrubar o ciclo, deixa
    # ajustar a CE no submenu e tenta de novo. (Se o SIGEF não devolver o
    # número depois do "Incluir", NÃO tenta de novo sozinho: a CE pode ter
    # sido criada, e repetir duplicaria.)
    while True:
        try:
            return executar_ce(context, processo, dados_ce), False
        except CEConfiguracaoIncompleta as erro:
            explicar_erro("Falta ajustar a configuração da CE", [str(erro)])
            if not _oferecer_configuracoes("ce", "CE", str(erro)):
                raise


def _oferecer_configuracoes(secao: str, nome: str, motivo: str) -> bool:
    """
    A configuração de uma etapa está incompleta (nada foi feito no SIGEF
    ainda): oferece abrir as Configurações nessa seção. True = a pessoa
    ajustou (o programa tenta de novo); False = preferiu parar.
    """
    linhas = [linha.strip(" -") for linha in motivo.splitlines() if linha.strip()]
    if not interacao.confirmar(
        f"Falta ajustar a configuração da {nome}",
        linhas + ["Nada foi feito no SIGEF ainda -- pode corrigir com calma."],
        sim=f"Abrir as configurações da {nome}",
        nao="Parar o processo aqui",
        tom="atencao",
    ):
        return False
    interacao.abrir_configuracoes(secao, f"Ajuste a configuração da {nome}", [
        "Arrume o que estiver em amarelo e clique em Salvar.",
        "Depois clique em “Voltar para o processo”: o programa continua de onde parou.",
    ])
    return True


def gerar_pps(context, ce: str, lancamentos: list[dict], dados: dict) -> list[dict]:
    """
    executar_pp_lote() com a mesma proteção da CE: se a configuração da PP
    estiver incompleta (ex: Crédito conta-corrente sem agência), nada foi
    preenchido no SIGEF ainda -- deixa ajustar no submenu da PP e tenta de novo.
    """
    while True:
        try:
            return executar_pp_lote(context, ce, lancamentos, dados["conta_pp"], dados)
        except PPConfiguracaoIncompleta as erro:
            explicar_erro("Falta ajustar a configuração da PP", [str(erro)])
            if not _oferecer_configuracoes("pp", "PP", str(erro)):
                raise


def garantir_config_ob(dados: dict, processo: str = None) -> None:
    """
    Antes da primeira OB: se a configuração da OB estiver incompleta (ou
    faltar a Conta OB), nada foi preenchido no SIGEF ainda -- deixa ajustar
    no submenu da OB e confere de novo. Responder N interrompe o ciclo.
    """
    while True:
        problemas = problemas_ob(config_ob(), dados)
        if not problemas:
            return
        explicar_erro("Falta ajustar a configuração da OB", problemas)
        if not _oferecer_configuracoes("ob", "OB", "\n".join(problemas)):
            raise OBConfiguracaoIncompleta("Configuração da OB incompleta: " + "; ".join(problemas))


def gerar_obs(context, dados: dict, lancamentos: list[dict], processo: str = None) -> list[dict]:
    """
    Gera UMA OB para todas as PPs do lote (as dos lançamentos que já têm PP
    e ainda não têm OB), com a conta OB compartilhada do SEI(1) e a
    configuração do submenu da OB. Todos esses lançamentos recebem o mesmo
    número de OB.

    Lançamento que já tem OB (de uma execução anterior) não entra de novo;
    sem PP, fica sem OB. Se a OB não puder ser gerada (ex: uma PP não
    aparece na busca), nenhum lançamento recebe OB e o resumo mostra
    pendente -- rodar de novo tenta outra vez, sem duplicar.

    Retorna a MESMA lista `lancamentos`, com a chave "ob" em cada item.
    """
    pendentes = []
    for item in lancamentos:
        if item.get("ob"):
            # Já tem OB de uma execução anterior -- pula pra não gerar duplicado.
            print(f"⏭️  O valor {item['valor']} já tem OB ({item['ob']}) de antes -- não faz de novo.")
        elif not item.get("pp"):
            print(f"⚠️  O valor {item['valor']} ficou sem PP -- por isso fica sem OB (veja o resumo no final).")
            item["ob"] = None
        else:
            pendentes.append(item)

    if not pendentes:
        salvar_sessao(lancamentos=lancamentos)
        return lancamentos

    garantir_config_ob(dados, processo)

    pps = [(item["pp"], item["valor_padronizado"]) for item in pendentes]
    print(f"🏦 Fazendo UMA OB para {len(pps)} PP(s): {', '.join(pp for pp, _ in pps)}")
    dados_ob = {**dados, "processo": processo or dados.get("processo")}
    try:
        numero_ob = executar_ob_lote(context, pps, dados["conta_ob"], dados_ob)
        if numero_ob is None:
            explicar_erro(
                "O SIGEF não confirmou a OB",
                [
                    "Olhe a tela do SIGEF no Chrome do programa.",
                    "Se a OB FOI feita: anote o número e chame quem cuida do sistema",
                    "   ANTES de rodar de novo (para não fazer outra OB).",
                    "Se apareceu uma mensagem de erro: leia, corrija e rode de novo com o MESMO processo.",
                ],
            )
    except OBConfiguracaoIncompleta:
        raise
    except Exception as erro:
        # Falhou (ex: PP não encontrada na busca): nenhum lançamento fica com
        # OB; o resumo mostra pendente e a próxima execução tenta de novo.
        explicar_erro(
            "A OB não foi feita",
            [
                f"Motivo: {erro}",
                "Nenhuma OB foi criada -- não há nada em dobro no SIGEF.",
                "O programa continua e baixa o que já está pronto.",
                "Depois, confira no SIGEF se todas as PPs aparecem para pagamento.",
                "Rode o programa de novo com o MESMO processo: ele tenta a OB outra vez.",
            ],
        )
        numero_ob = None

    for item in pendentes:
        item["ob"] = numero_ob

    # Salva logo -- se o script parar depois, a OB gerada não se perde e
    # não seria gerada de novo (duplicada) na próxima execução.
    salvar_sessao(lancamentos=lancamentos)
    return lancamentos


def reiniciar_sessao_para_novo_processo() -> None:
    """
    Limpa, na sessão salva, só os dados que pertencem ao processo que
    ACABOU DE SER concluído (processo, CE, a OB avulsa e a lista de
    lançamentos com suas NL/PP/OB/anexos) -- antes de começar o ciclo do
    PRÓXIMO processo, no loop de main().

    Sem isso, a Etapa SEI (1) ofereceria reaproveitar a CE e os
    lançamentos (já com NL/PP/OB/anexos preenchidos) do processo
    ANTERIOR -- e as etapas seguintes pulariam tudo achando que o
    processo NOVO já tivesse sido feito, sem gerar nada de fato.

    Os demais dados (CNPJ/CPF, contas, escola, parcela, mês de
    referência, programa) continuam salvos e disponíveis pra
    reaproveitar -- a tabela da Etapa SEI (1) já vem preenchida com eles.
    """
    salvar_sessao(processo="", ce="", ob="", lancamentos=[])


def preparar_sessao_login(context) -> None:
    """
    Abre (ou reaproveita, se já estiverem abertas) as abas do SEI e do
    SIGEF nesse Chrome -- só NAVEGA até elas (mesma obter_ou_criar_aba
    usada por todas as etapas), sem clicar em nada nem preencher nada --
    e pede uma confirmação de que o usuário já entrou com a própria
    conta nos dois sistemas antes de seguir com o resto do fluxo.

    Chamada por garantir_chrome_pronto() só quando o Chrome acabou de
    ser (re)conectado -- ou seja, uma vez por Chrome de depuração aberto,
    não uma vez por processo.
    """
    interacao.avisar("etapa", chave="LOGIN", titulo="Entrar no SEI e no SIGEF", texto="")
    caixa("🔐 ENTRAR NO SEI E NO SIGEF", ["Abrindo o SEI e o SIGEF no Chrome do programa... aguarde."])
    interacao.andamento("Abrindo o SEI e o SIGEF no Chrome do programa")

    obter_ou_criar_aba(context, dominio="sei.sistemas.ro.gov.br", url_navegacao=URL_SEI)
    obter_ou_criar_aba(context, dominio="sigef.sefin.ro.gov.br", url_navegacao=URL_SIGEF)

    interacao.continuar(
        "Entre no SEI e no SIGEF",
        ["Se você já está dentro dos dois, é só clicar no botão abaixo."],
        rotulo="Já entrei nos dois — continuar",
        passos=[
            "Vá até o Google Chrome que o programa abriu.",
            "Na aba do SEI, entre com seu usuário e senha.",
            "Na aba do SIGEF, entre com seu usuário e senha.",
            "Volte para esta janela.",
        ],
    )


def garantir_chrome_pronto(estado: dict):
    """
    Garante que existe um Chrome de depuração aberto e conectado pra
    automação, guardando playwright/browser/context em `estado` (dict
    mutável, criado vazio em main() e reaproveitado a cada chamada) --
    e só pede a confirmação de login (preparar_sessao_login) na
    PRIMEIRA vez que conecta, ou de novo se o Chrome de depuração tiver
    sido fechado nesse meio tempo.

    Se o Chrome de depuração foi fechado (browser.is_connected() ==
    False), conectar_chrome() abre um Chrome novo automaticamente -- e
    como esse Chrome novo começa sem nenhuma aba aberta, o login
    também precisa ser refeito, por isso preparar_sessao_login() roda
    de novo nesse caso.

    Retorna o `context` pronto pra uso.
    """
    browser = estado.get("browser")
    if browser is not None and browser.is_connected():
        return estado["context"]

    if estado.get("playwright") is not None:
        # Chrome de depuração antigo caiu/foi fechado -- encerra essa
        # conexão do Playwright antes de abrir outra.
        try:
            estado["playwright"].stop()
        except Exception:
            pass
        print("\n⚠️  O Chrome do programa foi fechado -- abrindo de novo (vai pedir para entrar no SEI e no SIGEF).")

    playwright, browser, context = conectar_chrome()
    estado.update(playwright=playwright, browser=browser, context=context)

    preparar_sessao_login(context)

    return context


def executar_ciclo(context) -> None:
    """
    Executa o ciclo completo de regularização pra UM processo:

        SEI(1) -> CE -> NL -> PP -> OB -> Anexar Documento -> SEI(2)

    Ver o docstring do módulo para a visão geral de cada etapa. Chamada
    repetidamente por main(), uma vez por processo.
    """
    aba_sei, processo, dados = executar_sei1(context)
    lancamentos = dados["lancamentos"]

    inicio_de_etapa("CE", "CE -- Despesa Certificada", f"O programa faz a CE no SIGEF com o Valor Total (R$ {dados['valor_total']}).")
    dados_ce = {**dados, "valor_padronizado": dados["valor_total_padronizado"]}
    ce, ce_reaproveitada = obter_ce(context, processo, dados_ce)

    if not ce_reaproveitada:
        # CE nova -- qualquer NL/PP/OB/anexo salvo de antes pertencia à
        # CE anterior e não vale mais pra essa. Limpa pra gerar tudo de
        # novo do zero (senão o "pular duplicado" de cada etapa ia pular
        # achando que já tinha sido feito nessa CE).
        for item in lancamentos:
            item.pop("nl", None)
            item.pop("pp", None)
            item.pop("ob", None)
            item.pop("anexo_baixado", None)
            item.pop("arquivos_anexar", None)

    inicio_de_etapa("NL", "NL -- Nota de Lançamento", f"O programa faz {len(lancamentos)} NL(s) no SIGEF, uma para cada valor.")
    lancamentos = executar_nl_lote(context, ce, lancamentos, dados)

    inicio_de_etapa("PP", "PP -- Preparação de Pagamento", f"O programa faz {len(lancamentos)} PP(s) no SIGEF, uma para cada valor.")
    lancamentos = gerar_pps(context, ce, lancamentos, dados)

    inicio_de_etapa("OB", "OB -- Ordem Bancária", "O programa faz UMA OB no SIGEF que paga todas as PPs.")
    lancamentos = gerar_obs(context, dados, lancamentos, processo)

    inicio_de_etapa("BAIXAR", "BAIXAR OS DOCUMENTOS", "O programa baixa do SIGEF os documentos da CE, NL, PP e OB.")
    lancamentos = executar_anexar_lote(context, processo, lancamentos)

    inicio_de_etapa("SEI", "COLOCAR NO SEI", f"O programa coloca os documentos dentro do processo {processo} no SEI.")
    executar_sei2(context, processo)

    resumo_final(processo, ce, lancamentos)


def resumo_final(processo: str, ce: str, lancamentos: list[dict]) -> dict:
    """O resumo do processo: no registro (texto) e no quadro do aplicativo."""
    caixa(f"📋 RESUMO -- Processo {processo} | CE {ce}")
    for i, item in enumerate(lancamentos, start=1):
        concluido = bool(item.get("ob")) and bool(item.get("anexo_baixado"))
        status = "✅" if concluido else "⚠️ "
        print(
            f"{status} {i}) Valor {item['valor']} | NE {item['nota_de_empenho']} -- "
            f"NL {item.get('nl')} | PP {item.get('pp')} | OB {item.get('ob')} | "
            f"Anexado: {'sim' if item.get('anexo_baixado') else 'não'}"
        )
    print("-" * 60)
    print("  ✅ = pronto      ⚠️  = ficou faltando alguma coisa")
    tudo_pronto = bool(lancamentos) and all(item.get("ob") and item.get("anexo_baixado") for item in lancamentos)
    if tudo_pronto:
        instrucao("Tudo pronto. Confira no SEI e assine (o programa NÃO assina).")
    else:
        instrucao(
            "Alguma linha tem ⚠️. Faça o processo de novo com o MESMO número:",
            "   o programa faz só o que faltou, sem repetir o que já está pronto.",
        )
    resumo = {
        "processo": processo,
        "ce": ce,
        "tudo_pronto": tudo_pronto,
        "lancamentos": [
            {"numero": i, "valor": item.get("valor"), "nota_de_empenho": item.get("nota_de_empenho"),
             "nl": item.get("nl"), "pp": item.get("pp"), "ob": item.get("ob"),
             "baixado": bool(item.get("anexo_baixado")),
             "pronto": bool(item.get("ob")) and bool(item.get("anexo_baixado"))}
            for i, item in enumerate(lancamentos, start=1)
        ],
    }
    interacao.avisar("resumo", resumo=resumo)
    global ULTIMO_RESUMO
    ULTIMO_RESUMO = resumo
    return resumo


ULTIMO_RESUMO = None


def perguntar_outro_processo() -> bool:
    """No fim de cada processo: fazer o próximo agora ou terminar por hoje."""
    resumo = ULTIMO_RESUMO or {}
    if resumo.get("tudo_pronto"):
        linhas = ["Tudo pronto. Confira no SEI e assine (o programa NÃO assina)."]
    else:
        linhas = ["Faltou alguma coisa (veja as linhas em amarelo). Faça o processo de novo com o MESMO número:",
                  "o programa faz só o que faltou, sem repetir nada."]
    return interacao.confirmar(
        f"Processo {resumo.get('processo') or ''} terminado".replace("  ", " "),
        linhas,
        sim="Fazer o próximo processo",
        nao="Terminar por hoje",
        tom="normal" if resumo.get("tudo_pronto") else "atencao",
        resumo=resumo or None,
    )


def _avisar_erro_inesperado(erro: Exception) -> None:
    """
    Em vez da "tela de erro" do Python (cheia de termos técnicos), mostra
    uma explicação simples do que fazer -- e guarda os detalhes técnicos
    em registro_de_erros.txt para quem cuida do sistema.
    """
    arquivo = registrar_detalhes_tecnicos("o programa parou")
    if arquivo:
        onde = f"Os detalhes técnicos foram guardados no arquivo: {arquivo}"
    else:
        onde = "Tire uma foto desta tela inteira."
    explicar_erro(
        "O programa parou por causa de um problema",
        [
            f"O problema foi: {erro}",
            "Tudo o que já foi feito está guardado.",
            "Confira se a internet, o SEI e o SIGEF estão funcionando.",
            "Clique em Começar de novo e use o MESMO processo.",
            "Se acontecer de novo, chame quem cuida do sistema.",
            onde,
        ],
    )


def main() -> None:
    """
    Ponto de entrada da automação.

    A cada volta do loop, garantir_chrome_pronto() garante o Chrome de
    depuração aberto e conectado -- abrindo um automaticamente se
    preciso, e pedindo a confirmação de login no SEI/SIGEF só na
    primeira vez (ou de novo, se o Chrome de depuração tiver sido
    fechado nesse meio tempo) -- e então executar_ciclo() roda pra um
    processo. Repete pro próximo processo até a pessoa clicar em
    "Terminar por hoje", ou no botão "Parar o programa" a qualquer momento.
    """
    caixa(
        "👋 BEM-VINDO AO ANEXAR DOCUMENTOS",
        [
            "Este programa faz a CE, NL, PP e OB no SIGEF e coloca",
            "os documentos no processo do SEI -- sozinho.",
            "Quando precisar de você, ele mostra a pergunta com botões.",
        ],
    )
    estado_chrome: dict = {}
    try:
        while True:
            context = garantir_chrome_pronto(estado_chrome)

            executar_ciclo(context)

            if not perguntar_outro_processo():
                print("👋 Programa encerrado. Já pode fechar esta janela. Até a próxima!")
                break
            reiniciar_sessao_para_novo_processo()
    except KeyboardInterrupt:
        caixa(
            "⏹️  PROGRAMA PARADO",
            [
                "Tudo o que já foi feito está guardado.",
                "Para continuar depois: clique em Começar e use o MESMO processo.",
                "O programa continua de onde parou, sem fazer nada em dobro.",
            ],
        )
    except Exception as erro:
        _avisar_erro_inesperado(erro)
    finally:
        if estado_chrome.get("playwright") is not None:
            estado_chrome["playwright"].stop()


if __name__ == "__main__":
    main()
