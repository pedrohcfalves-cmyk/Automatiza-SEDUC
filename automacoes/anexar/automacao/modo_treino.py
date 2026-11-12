"""
MODO TREINO -- um processo de mentira, para aprender a usar o aplicativo.

Mostra as MESMAS telas do programa de verdade (fluxo.py): entrar no SEI e
no SIGEF, o número do processo, a tabela dos dados (todos de uma vez, com
os lançamentos), o quadro "Confira os dados", o andamento de cada etapa e
o resumo do fim. Mas NÃO abre o Chrome e NÃO mexe no SEI nem no SIGEF: só
espera um pouco em cada etapa, como se estivesse trabalhando.

Como usar: no aplicativo, ligue "Modo treino" (no menu à esquerda) e
clique em Começar. Os tempos do treino vão para dados/relatorios_simulacao/
e NÃO entram nas Estatísticas nem no Relatório do mês.

Também é usado pelos testes (testes/test_aplicativo.py).

Variáveis: ANEXAR_SESSAO_SIMULADA (arquivo da sessão do treino),
ANEXAR_DEMO_PAUSA (segundos de "trabalho" por item; padrão 1) e
ANEXAR_DEMO_FALHA_OB (simula uma OB que não foi feita).

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import json
import os
import time

from automacoes.geral import gravar_json
from automacoes.anexar import caminhos
from automacoes.anexar.automacao import dados_processo, interacao

CAMINHO_SESSAO = os.environ.get("ANEXAR_SESSAO_SIMULADA") or caminhos.ARQUIVO_SESSAO_TREINO
PAUSA = float(os.environ.get("ANEXAR_DEMO_PAUSA", "1"))
LARGURA = 60
PASSOS = ["CE", "NL", "PP", "OB", "BAIXAR", "SEI"]

# Na primeira vez, a tabela do treino já vem com um exemplo (menos os lançamentos).
EXEMPLO = {
    "cnpj_cpf": "03.508.155/0001-21",
    "municipio": "Porto Velho",
    "escola": "ESCOLA DE TREINO",
    "conta_pp": "105805",
    "conta_ob": "105805",
    "parcela": "7",
    "mes_referencia": "10",
    "programa": "PROAFI",
    "valor_total": "300,00",
}


# ============================================================ iguais às do utils.py (sem o Playwright)


def carregar_sessao() -> dict:
    try:
        with open(CAMINHO_SESSAO, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        return {}


def salvar_sessao(**valores) -> None:
    sessao = carregar_sessao()
    sessao.update(valores)
    caminhos.garantir_pasta(CAMINHO_SESSAO)
    gravar_json(CAMINHO_SESSAO, sessao)
    interacao.avisar("sessao", sessao=interacao.resumo_da_sessao(sessao))


def caixa(titulo, linhas=(), borda="="):
    print("\n" + borda * LARGURA)
    print(f"  {titulo}")
    print(borda * LARGURA)
    for linha in linhas:
        print(f"  {linha}")
    if linhas:
        print(borda * LARGURA)


def explicar_erro(o_que_aconteceu, o_que_fazer=()):
    interacao.avisar("erro", titulo=str(o_que_aconteceu), passos=[str(p) for p in o_que_fazer])
    caixa("❌ ATENÇÃO: " + o_que_aconteceu, borda="!")
    if o_que_fazer:
        print("  O QUE FAZER:")
        for numero, passo in enumerate(o_que_fazer, start=1):
            print(f"    {numero}. {passo}")
        print("!" * LARGURA)


def inicio_de_etapa(chave, titulo, o_que_faz):
    interacao.avisar("etapa", chave=chave, titulo=titulo, texto=o_que_faz)
    numero = PASSOS.index(chave) + 1
    caixa(f"⏳ PASSO {numero} de {len(PASSOS)} -- {titulo}",
          [o_que_faz, "", "✋ NÃO mexa no Chrome do programa. Só acompanhe."])


def _trabalhar(fracao: float = 1.0) -> None:
    time.sleep(PAUSA * fracao)


# ============================================================ o "processo" de treino


def preparar_sessao_login(context):
    interacao.avisar("etapa", chave="LOGIN", titulo="Entrar no SEI e no SIGEF", texto="")
    caixa("🔐 ENTRAR NO SEI E NO SIGEF (TREINO)")
    interacao.continuar(
        "Entre no SEI e no SIGEF",
        ["É um treino: aqui não precisa entrar em nada, é só continuar."],
        rotulo="Já entrei nos dois — continuar",
        passos=[
            "Vá até o Google Chrome que o programa abriu.",
            "Na aba do SEI, entre com seu usuário e senha.",
            "Na aba do SIGEF, entre com seu usuário e senha.",
            "Volte para esta janela.",
        ],
    )


def executar_sei1(context):
    sessao = carregar_sessao()
    processo = interacao.pedir_texto(
        "Qual é o processo?", "Número do processo no SEI",
        atual=sessao.get("processo") or "", exemplo="0029.002180/2026-93",
        ajuda="No treino, qualquer número serve.", rotulo_botao="Abrir o processo no SEI",
    )
    interacao.andamento(f"Abrindo o processo {processo} no SEI (treino)")
    _trabalhar(0.5)
    base = {**EXEMPLO, **{chave: valor for chave, valor in sessao.items() if valor}}
    if sessao.get("processo") != processo:
        base["lancamentos"] = []
        base["ce"] = ""
    salvar_sessao(processo=processo, ce=base.get("ce") or "", lancamentos=base.get("lancamentos") or [])
    dados = dados_processo.coletar(processo, base, treino=True)
    salvar_sessao(**dados)
    return None, processo, dados


def obter_ce(context, processo, dados_ce):
    sessao = carregar_sessao()
    if sessao.get("ce"):
        if interacao.confirmar(
            "Já existe uma CE feita antes",
            [f"CE guardada: {sessao['ce']}",
             "Use a CE guardada se você está CONTINUANDO este mesmo processo.",
             "Faça uma CE nova se é um processo NOVO."],
            sim=f"Usar a CE guardada ({sessao['ce']})", nao="Fazer uma CE nova", tom="atencao",
        ):
            return sessao["ce"], True
    interacao.andamento(f"Preenchendo a CE no SIGEF (Valor Total R$ {dados_ce.get('valor_total')})")
    _trabalhar()
    print("✅ CE feita: 018705")
    salvar_sessao(ce="018705")
    return "018705", False


def executar_ciclo(context):
    _aba, processo, dados = executar_sei1(context)
    lancamentos = dados["lancamentos"]
    inicio_de_etapa("CE", "CE -- Despesa Certificada", f"O programa faz a CE no SIGEF com o Valor Total (R$ {dados['valor_total']}).")
    ce, reaproveitada = obter_ce(context, processo, dados)
    if not reaproveitada:
        for item in lancamentos:
            for chave in ("nl", "pp", "ob", "anexo_baixado"):
                item.pop(chave, None)
        salvar_sessao(lancamentos=lancamentos)
    for chave, titulo in (("NL", "NL -- Nota de Lançamento"), ("PP", "PP -- Preparação de Pagamento")):
        inicio_de_etapa(chave, titulo, f"O programa faz {len(lancamentos)} {chave}(s) no SIGEF, uma para cada valor.")
        for numero, item in enumerate(lancamentos, start=1):
            if item.get(chave.lower()):
                print(f"⏭️  O valor {item['valor']} já tem {chave} ({item[chave.lower()]}) de antes -- não faz de novo.")
                continue
            interacao.andamento(f"Fazendo a {chave} do valor R$ {item['valor']}", numero, len(lancamentos))
            _trabalhar()
            item[chave.lower()] = f"0662{numero:02d}" if chave == "NL" else f"2026PP03977{numero}"
            print(f"✅ {chave} feita para o valor {item['valor']}: {item[chave.lower()]}")
            salvar_sessao(lancamentos=lancamentos)
    inicio_de_etapa("OB", "OB -- Ordem Bancária", "O programa faz UMA OB no SIGEF que paga todas as PPs.")
    interacao.andamento(f"Preenchendo a OB que paga {len(lancamentos)} PP(s)")
    _trabalhar()
    if os.environ.get("ANEXAR_DEMO_FALHA_OB"):
        explicar_erro("A OB não foi feita", ["Motivo: PP não encontrada na busca.",
                                             "Faça o processo de novo com o MESMO número."])
    else:
        for item in lancamentos:
            item.setdefault("ob", "2026OB012345")
        print("✅ OB feita: 2026OB012345")
    salvar_sessao(lancamentos=lancamentos)
    inicio_de_etapa("BAIXAR", "BAIXAR OS DOCUMENTOS", "O programa baixa do SIGEF os documentos da CE, NL, PP e OB.")
    for numero, item in enumerate(lancamentos, start=1):
        interacao.andamento(f"Baixando os documentos do valor R$ {item['valor']}", numero, len(lancamentos))
        _trabalhar(0.5)
        item["anexo_baixado"] = bool(item.get("ob"))
        print(f"✅ Documentos do valor {item['valor']} baixados." if item["anexo_baixado"]
              else f"⚠️  Valor {item['valor']} ficou sem OB -- documentos não baixados.")
        salvar_sessao(lancamentos=lancamentos)
    inicio_de_etapa("SEI", "COLOCAR NO SEI", f"O programa coloca os documentos dentro do processo {processo} no SEI.")
    interacao.andamento("Colocando a CE, as NLs, as PPs e a OB no processo")
    _trabalhar()
    interacao.continuar(
        "Confira e assine no SEI",
        [f"Os documentos CE, NL, PP e OB já estão no processo {processo} (treino)."],
        rotulo="Terminei no SEI — continuar",
        passos=["Vá até o Chrome do programa, na aba do SEI.", "Confira os documentos.",
                "Assine (o programa NÃO assina nada).", "Volte para esta janela."],
    )
    resumo_final(processo, ce, lancamentos)


ULTIMO_RESUMO = None


def resumo_final(processo, ce, lancamentos):
    global ULTIMO_RESUMO
    caixa(f"📋 RESUMO -- Processo {processo} | CE {ce}")
    for numero, item in enumerate(lancamentos, start=1):
        pronto = item.get("ob") and item.get("anexo_baixado")
        print(f"{'✅' if pronto else '⚠️ '} {numero}) Valor {item['valor']} -- NL {item.get('nl')} | "
              f"PP {item.get('pp')} | OB {item.get('ob')}")
    tudo_pronto = bool(lancamentos) and all(item.get("ob") and item.get("anexo_baixado") for item in lancamentos)
    ULTIMO_RESUMO = {
        "processo": processo, "ce": ce, "tudo_pronto": tudo_pronto,
        "lancamentos": [{"numero": numero, "valor": item.get("valor"), "nota_de_empenho": item.get("nota_de_empenho"),
                         "nl": item.get("nl"), "pp": item.get("pp"), "ob": item.get("ob"),
                         "baixado": bool(item.get("anexo_baixado")),
                         "pronto": bool(item.get("ob")) and bool(item.get("anexo_baixado"))}
                        for numero, item in enumerate(lancamentos, start=1)],
    }
    interacao.avisar("resumo", resumo=ULTIMO_RESUMO)
    return ULTIMO_RESUMO


def perguntar_outro_processo() -> bool:
    resumo = ULTIMO_RESUMO or {}
    linhas = (["Tudo pronto. No programa de verdade, agora você confere no SEI e assina."]
              if resumo.get("tudo_pronto") else
              ["Faltou alguma coisa (veja as linhas em amarelo). No programa de verdade, é só fazer o",
               "processo de novo com o MESMO número: ele faz só o que faltou."])
    return interacao.confirmar(
        f"Processo {resumo.get('processo') or ''} terminado (treino)", linhas,
        sim="Fazer outro treino", nao="Terminar o treino",
        tom="normal" if resumo.get("tudo_pronto") else "atencao", resumo=resumo or None,
    )


def main():
    caixa("👋 BEM-VINDO AO TREINO DO ANEXAR DOCUMENTOS", [
        "Nada aqui mexe no SEI ou no SIGEF.",
        "As telas são as mesmas do programa de verdade.",
    ])
    try:
        preparar_sessao_login(None)
        while True:
            executar_ciclo(None)
            if not perguntar_outro_processo():
                print("👋 Treino encerrado. Até a próxima!")
                break
            salvar_sessao(processo="", ce="", lancamentos=[])
    except KeyboardInterrupt:
        caixa("⏹️  PROGRAMA PARADO", ["Tudo o que já foi feito está guardado."])


if __name__ == "__main__":
    main()
