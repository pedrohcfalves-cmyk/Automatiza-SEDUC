"""
A conversa do programa com a pessoa -- SEMPRE por botões e tabelas.

Nenhuma parte do programa pede para "digitar uma letra e apertar ENTER".
Toda pergunta é um PEDIDO (um dicionário) que o aplicativo desenha na tela:

    tipo "botoes"        uma mensagem e botões (Sim / Não, Continuar, opções)
    tipo "formulario"    uma tabela para preencher (ex: os dados do processo,
                         todos de uma vez, com a tabela de lançamentos)
    tipo "conferencia"   o quadro "Confira os dados", com os botões Começar /
                         Corrigir / Configurações
    tipo "configuracoes" abre a tela de Configurações do aplicativo e espera
                         a pessoa clicar em "Voltar para o processo"

e a resposta volta como o VALOR do botão clicado (e, no formulário, o que
foi preenchido). Quem liga isto ao aplicativo é anexar/aplicativo/executor.py
(definir_canal). Além das perguntas, o programa AVISA o aplicativo do que
está fazendo (avisar / andamento): é assim que a tela mostra, ao vivo, a
etapa, o item sendo feito e os números que o SIGEF vai devolvendo.

Sem o aplicativo (por exemplo, quem desenvolve rodando uma etapa sozinha
no terminal), _no_terminal() mostra o mesmo pedido como uma lista
numerada. É só para quem desenvolve: quem usa o programa usa o aplicativo.

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import itertools
import json

_perguntar_pelo_aplicativo = None   # função(pedido: dict) -> resposta
_avisar_o_aplicativo = None         # função(tipo: str, dados: dict) -> None
_numeros = itertools.count(1)


def definir_canal(perguntar=None, avisar=None) -> None:
    """Liga as perguntas e os avisos ao aplicativo (None = volta para o terminal)."""
    global _perguntar_pelo_aplicativo, _avisar_o_aplicativo
    _perguntar_pelo_aplicativo = perguntar
    _avisar_o_aplicativo = avisar


# ============================================================ avisos (sem resposta)


def avisar(tipo: str, **dados) -> None:
    """Conta ao aplicativo o que está acontecendo (etapa, erro, sessão, resumo...)."""
    if _avisar_o_aplicativo is not None:
        try:
            _avisar_o_aplicativo(tipo, dados)
        except Exception:   # um aviso nunca derruba a automação
            pass


def resumo_da_sessao(sessao: dict) -> dict:
    """O que a tela mostra ao vivo: o processo, a CE e cada lançamento com NL/PP/OB."""
    sessao = sessao or {}
    return {
        "processo": sessao.get("processo") or "",
        "ce": sessao.get("ce") or "",
        "escola": sessao.get("escola") or "",
        "valor_total": sessao.get("valor_total") or "",
        "lancamentos": [
            {
                "valor": item.get("valor"),
                "nota_de_empenho": item.get("nota_de_empenho"),
                "nl": item.get("nl"),
                "pp": item.get("pp"),
                "ob": item.get("ob"),
                "baixado": bool(item.get("anexo_baixado")),
            }
            for item in (sessao.get("lancamentos") or [])
            if isinstance(item, dict)
        ],
    }


def andamento(texto: str, atual: int = None, total: int = None) -> None:
    """O que o programa está fazendo AGORA (ex: 'Fazendo a NL do valor R$ 100,00', 2 de 3)."""
    contagem = f" ({atual} de {total})" if atual and total else ""
    print(f"   ⏳ {texto}{contagem}")
    avisar("andamento", texto=texto, atual=atual, total=total)


# ============================================================ peças dos pedidos


def botao(valor: str, rotulo: str, estilo: str = "normal", icone: str = None,
          ajuda: str = None, desabilitado: bool = False) -> dict:
    """Um botão. estilo: principal (azul), normal, perigo (vermelho)."""
    return {"valor": valor, "rotulo": rotulo, "estilo": estilo, "icone": icone,
            "ajuda": ajuda, "desabilitado": bool(desabilitado)}


def campo(chave: str, rotulo: str, tipo: str = "texto", valor: str = "", anterior: str = None,
          exemplo: str = None, ajuda: str = None, opcoes: list = None, obrigatorio: bool = True,
          maximo: int = None) -> dict:
    """
    Uma linha da tabela de um formulário. tipo: texto, valor (R$), mes
    (lista de meses) ou lista (opcoes = [[valor, rótulo], ...]).
    `anterior` = o que foi usado da última vez (aparece ao lado).
    """
    return {"chave": chave, "rotulo": rotulo, "tipo": tipo, "valor": "" if valor is None else str(valor),
            "anterior": anterior, "exemplo": exemplo, "ajuda": ajuda, "opcoes": opcoes,
            "obrigatorio": obrigatorio, "maximo": maximo}


# ============================================================ perguntas


def perguntar(pedido: dict):
    """Manda o pedido para a tela e espera a resposta (o valor do botão clicado...)."""
    pedido = {"id": next(_numeros), "linhas": [], "tom": "normal", **pedido}
    pedido["linhas"] = [str(linha) for linha in pedido.get("linhas") or []]
    if _perguntar_pelo_aplicativo is not None:
        return _perguntar_pelo_aplicativo(pedido)
    return _no_terminal(pedido)


def _valor_do_botao(resposta) -> str:
    if isinstance(resposta, dict):
        return str(resposta.get("botao") or resposta.get("valor") or "")
    return "" if resposta is None else str(resposta)


def escolher(titulo: str, linhas=(), botoes=(), tom: str = "normal", **extras) -> str:
    """Mensagem + botões. Devolve o `valor` do botão clicado."""
    botoes = [b if isinstance(b, dict) else botao(*b) for b in botoes]
    validos = {b["valor"] for b in botoes if not b.get("desabilitado")}
    while True:
        valor = _valor_do_botao(perguntar({"tipo": "botoes", "titulo": titulo, "linhas": list(linhas),
                                            "botoes": botoes, "tom": tom, **extras}))
        if valor in validos:
            return valor


def confirmar(titulo: str, linhas=(), sim: str = "Sim", nao: str = "Não", tom: str = "normal", **extras) -> bool:
    """Sim/Não com botões (os rótulos dizem o que cada um faz)."""
    return escolher(titulo, linhas, [botao("sim", sim, "principal", "check"), botao("nao", nao, "normal", "voltar")],
                    tom=tom, **extras) == "sim"


def continuar(titulo: str, linhas=(), rotulo: str = "Continuar", passos=None, tom: str = "normal", **extras) -> None:
    """Uma pausa: explica o que fazer (passos numerados) e espera o clique em Continuar."""
    escolher(titulo, linhas, [botao("continuar", rotulo, "principal", "check")], tom=tom,
             passos=list(passos or []), **extras)


def preencher(titulo: str, campos: list, linhas=(), botoes=None, erros: dict = None,
              lancamentos: dict = None, **extras) -> dict:
    """
    Formulário em tabela. Devolve {"botao": valor, "valores": {chave: texto},
    "lancamentos": [{"valor", "nota_de_empenho"}] ou None}. Quem chamou
    confere os valores e, se algo estiver errado, chama de novo com `erros`
    ({chave: mensagem}) -- a tela mostra cada erro ao lado do campo.
    """
    botoes = botoes or [botao("enviar", "Continuar", "principal", "check")]
    resposta = perguntar({"tipo": "formulario", "titulo": titulo, "linhas": list(linhas), "campos": campos,
                          "botoes": botoes, "erros": erros or {}, "lancamentos": lancamentos, **extras})
    if not isinstance(resposta, dict):
        resposta = {"botao": _valor_do_botao(resposta)}
    valores = resposta.get("valores") if isinstance(resposta.get("valores"), dict) else {}
    itens = resposta.get("lancamentos")
    if isinstance(itens, list):
        itens = [{"valor": str((item or {}).get("valor") or "").strip(),
                  "nota_de_empenho": str((item or {}).get("nota_de_empenho") or "").strip()}
                 for item in itens if isinstance(item, dict)]
    else:
        itens = None
    return {
        "botao": str(resposta.get("botao") or botoes[0]["valor"]),
        "valores": {str(chave): ("" if valor is None else str(valor)).strip() for chave, valor in valores.items()},
        "lancamentos": itens,
    }


def pedir_texto(titulo: str, rotulo: str, atual: str = "", exemplo: str = None, ajuda: str = None,
                rotulo_botao: str = "Continuar", linhas=()) -> str:
    """Um campo só (ex: o número do processo). Não aceita em branco."""
    erros = {}
    while True:
        resposta = preencher(titulo, [campo("texto", rotulo, valor=atual or "", anterior=atual or None,
                                            exemplo=exemplo, ajuda=ajuda)],
                             linhas=linhas, botoes=[botao("enviar", rotulo_botao, "principal", "check")], erros=erros)
        texto = resposta["valores"].get("texto", "").strip()
        if texto:
            return texto
        erros = {"texto": "Este campo não pode ficar em branco."}


def conferir(pedido: dict) -> str:
    """O quadro "Confira os dados" (montado por dados_processo.pedido_conferencia)."""
    botoes = pedido.get("botoes") or []
    validos = {b["valor"] for b in botoes if not b.get("desabilitado")}
    while True:
        valor = _valor_do_botao(perguntar({**pedido, "tipo": "conferencia"}))
        if valor in validos:
            return valor


def abrir_configuracoes(secao: str = None, titulo: str = "Ajuste as configurações", linhas=()) -> None:
    """
    Abre a tela de Configurações (na seção `secao`: global, ce, pp ou ob) e
    espera a pessoa clicar em "Voltar para o processo". O que ela salvar lá
    já vale quando o programa continuar.
    """
    perguntar({"tipo": "configuracoes", "secao": secao, "titulo": titulo, "linhas": list(linhas),
               "botoes": [botao("pronto", "Voltar para o processo", "principal", "check")]})


# ============================================================ sem aplicativo (só para quem desenvolve)


def _ler(mensagem: str) -> str:
    return input(mensagem)


def _mostrar_cabecalho(pedido: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  {pedido.get('titulo') or ''}")
    print("=" * 60)
    for linha in pedido.get("linhas") or []:
        print(f"  {linha}")
    for numero, passo in enumerate(pedido.get("passos") or [], start=1):
        print(f"    {numero}. {passo}")


def _escolher_no_terminal(botoes: list) -> str:
    ativos = [b for b in botoes if not b.get("desabilitado")]
    if len(ativos) == 1:
        _ler(f"  ({ativos[0]['rotulo']}) ")
        return ativos[0]["valor"]
    for numero, b in enumerate(ativos, start=1):
        print(f"   {numero}) {b['rotulo']}")
    while True:
        texto = _ler("  Número da opção: ").strip()
        if texto.isdigit() and 1 <= int(texto) <= len(ativos):
            return ativos[int(texto) - 1]["valor"]


def _no_terminal(pedido: dict):
    tipo = pedido.get("tipo")
    _mostrar_cabecalho(pedido)
    if tipo == "formulario":
        for chave, mensagem in (pedido.get("erros") or {}).items():
            print(f"  ⚠️  {chave}: {mensagem}")
        valores = {}
        for item in pedido.get("campos") or []:
            atual = item.get("valor") or ""
            texto = _ler(f"  {item['rotulo']} [{atual}]: ").strip()
            valores[item["chave"]] = texto or atual
        lancamentos = None
        if pedido.get("lancamentos") is not None:
            atuais = pedido["lancamentos"].get("itens") or []
            print("  Lançamentos (valor;nota de empenho por linha; linha vazia termina; nada = manter):")
            for item in atuais:
                print(f"     {item.get('valor')};{item.get('nota_de_empenho')}")
            novos = []
            while True:
                linha = _ler("   > ").strip()
                if not linha:
                    break
                valor, _, empenho = linha.partition(";")
                novos.append({"valor": valor.strip(), "nota_de_empenho": empenho.strip()})
            lancamentos = novos or atuais
        return {"botao": pedido["botoes"][0]["valor"], "valores": valores, "lancamentos": lancamentos}
    if tipo == "conferencia":
        for grupo in pedido.get("dados") or []:
            print(f"  {grupo[0]:<24}: {grupo[1]}")
        for item in (pedido.get("lancamentos") or {}).get("itens") or []:
            print(f"     {item['numero']}. R$ {item['valor']:<12} NE {item['nota_de_empenho']}")
        for problema in pedido.get("problemas") or []:
            print(f"  ⚠️  {problema}")
    if tipo == "configuracoes":
        print("  (Ajuste as configurações pelo aplicativo, na tela Configurações.)")
    if pedido.get("resumo"):
        print("  " + json.dumps(pedido["resumo"], ensure_ascii=False))
    return _escolher_no_terminal(pedido.get("botoes") or [botao("continuar", "Continuar")])
