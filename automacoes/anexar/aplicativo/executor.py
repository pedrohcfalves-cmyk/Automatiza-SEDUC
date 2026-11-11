"""
Ponte entre o aplicativo (nucleo.py) e a automação (fluxo.py).

O aplicativo roda este arquivo num processo separado, que roda a
automação de sempre (anexar/automacao/fluxo.py -- ou o modo treino). Toda
conversa com a pessoa passa por anexar/automacao/interacao.py, que aqui é
ligado ao aplicativo (definir_canal):

1. Cada PERGUNTA vira um evento "pergunta" com o pedido inteiro (botões,
   tabela dos dados, "Confira os dados", configurações). A tela desenha o
   pedido e devolve a resposta (o botão clicado e o que foi preenchido)
   numa linha de JSON. Nada de digitar letras.
2. Cada AVISO (etapa, andamento, erro, sessão, resumo) vira um evento --
   é assim que a tela mostra, ao vivo, o que o programa está fazendo e as
   NL/PP/OB que vão sendo feitas.
3. As etapas e as perguntas são cronometradas pelo Medidor (metricas.py)
   para os relatórios (tempo da máquina x tempo de atenção humana).
4. O botão "Parar" do aplicativo manda uma linha de controle; aqui ela vira
   o mesmo KeyboardInterrupt do Ctrl+C, e a automação para do jeito que já
   sabe parar (guardando tudo).

Protocolo (stdout): texto normal (o registro técnico) passa direto; um evento é
    \\x1e{"tipo": "...", ...}\\n
Protocolo (stdin): cada linha é a resposta da pergunta aberta (JSON); a
linha \\x1ePARAR pede para parar.

Uso:  python -u -m automacoes.anexar.aplicativo.executor automacao

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""
import _thread
import builtins
import importlib
import json
import os
import queue
import signal
import sys
import threading

from automacoes.anexar import caminhos
from automacoes.anexar.automacao import interacao

MARCA_EVENTO = "\x1e"
COMANDO_PARAR = MARCA_EVENTO + "PARAR"
MODULO_PADRAO = "automacoes.anexar.automacao.fluxo"
MODULO_TREINO = "automacoes.anexar.automacao.modo_treino"

_respostas: "queue.Queue[str | None]" = queue.Queue()
_parar = threading.Event()
_esperando_resposta = threading.Event()
_input_original = builtins.input
medidor = None


def emitir(tipo: str, **dados) -> None:
    """Manda um evento para o aplicativo (uma linha própria na saída)."""
    try:
        sys.stdout.write(MARCA_EVENTO + json.dumps({"tipo": tipo, **dados}, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _ler_entrada() -> None:
    """Thread: lê as respostas que o aplicativo manda (uma por linha)."""
    for linha in sys.stdin:
        linha = linha.rstrip("\r\n")
        if linha == COMANDO_PARAR:
            _parar.set()
            _respostas.put(None)
            if not _esperando_resposta.is_set():
                # Parado no meio de uma etapa (não numa pergunta): mesmo
                # efeito do Ctrl+C.
                _thread.interrupt_main()
            continue
        _respostas.put(linha)
    # Aplicativo fechou a conexão: as respostas que já chegaram ainda valem;
    # depois delas, a próxima pergunta para o programa.
    _respostas.put(None)


def _esperar_resposta() -> str:
    if _parar.is_set():
        raise KeyboardInterrupt
    if medidor:
        medidor.antes_da_pergunta()
    _esperando_resposta.set()
    try:
        while True:
            try:
                resposta = _respostas.get(timeout=0.25)
            except queue.Empty:
                continue
            if resposta is None or _parar.is_set():
                raise KeyboardInterrupt
            return resposta
    finally:
        _esperando_resposta.clear()
        if medidor:
            medidor.depois_da_pergunta()


def _decodificar(linha: str):
    try:
        return json.loads(linha)
    except (json.JSONDecodeError, ValueError):
        return linha     # texto simples: vale como o valor do botão


def perguntar(pedido: dict):
    """interacao.perguntar() quando o programa roda pelo aplicativo."""
    emitir("pergunta", pedido=pedido)
    print(f"\n❓ {pedido.get('titulo') or 'Pergunta'}")
    resposta = _decodificar(_esperar_resposta())
    print(f"   ↳ resposta: {_resumo_da_resposta(resposta)}")
    emitir("respondido", id=pedido.get("id"))
    return resposta


def _resumo_da_resposta(resposta) -> str:
    if isinstance(resposta, dict):
        partes = [str(resposta.get("botao") or "")]
        if resposta.get("valores"):
            partes.append(", ".join(f"{c}={v}" for c, v in resposta["valores"].items()))
        if resposta.get("lancamentos"):
            partes.append(f"{len(resposta['lancamentos'])} lançamento(s)")
        return " | ".join(p for p in partes if p)
    return str(resposta)


def avisar(tipo: str, dados: dict) -> None:
    """interacao.avisar() quando o programa roda pelo aplicativo."""
    if medidor:
        if tipo == "etapa" and dados.get("chave"):
            medidor.inicio_etapa(dados["chave"])
        elif tipo == "erro":
            medidor.registrar_erro(dados.get("titulo") or "")
    emitir(tipo, **dados)


def _input_que_sobrou(mensagem: str = "") -> str:
    """
    Se alguma parte do programa ainda chamar input() (não devia), a tela
    mostra um campo com Continuar -- nunca fica travada sem botão.
    """
    pedido = {"id": 0, "tipo": "formulario", "titulo": str(mensagem).strip() or "O programa precisa de uma resposta",
              "linhas": [], "campos": [interacao.campo("texto", "Resposta", obrigatorio=False)],
              "botoes": [interacao.botao("enviar", "Continuar", "principal", "check")], "erros": {}}
    resposta = perguntar(pedido)
    if isinstance(resposta, dict):
        return str((resposta.get("valores") or {}).get("texto") or "")
    return str(resposta)


def _resumo_sessao(sessao: dict) -> dict:
    return interacao.resumo_da_sessao(sessao)


def instalar_na_automacao(principal) -> None:
    """Liga o Medidor nas funções do fluxo (ciclo, SEI 1, CE guardada)."""
    carregar_sessao = getattr(principal, "carregar_sessao")

    ciclo_original = principal.executar_ciclo

    def executar_ciclo(context):
        medidor.inicio_ciclo()
        emitir("ciclo_inicio")
        emitir("etapa", chave="SEI1", titulo="Dados do processo", texto="Confira os dados do processo no SEI.")
        status = "erro"
        try:
            resultado = ciclo_original(context)
            status = "ok"
            return resultado
        except KeyboardInterrupt:
            status = "interrompido"
            raise
        finally:
            try:
                sessao = carregar_sessao()
                registro = medidor.fim_ciclo(status, sessao)
                emitir("ciclo_fim", registro=registro, sessao=_resumo_sessao(sessao))
            except Exception as erro:  # o relatório nunca derruba a automação
                emitir("aviso_relatorio", texto=f"Não foi possível guardar os dados do relatório: {erro}")

    principal.executar_ciclo = executar_ciclo

    sei1_original = principal.executar_sei1

    def executar_sei1(context, *args, **kwargs):
        resultado = sei1_original(context, *args, **kwargs)
        try:
            medidor.guardar_lancamentos_iniciais(resultado[2].get("lancamentos"))
            emitir("sessao", sessao=_resumo_sessao(carregar_sessao()))
        except Exception:
            pass
        return resultado

    principal.executar_sei1 = executar_sei1

    obter_ce_original = principal.obter_ce

    def obter_ce(*args, **kwargs):
        ce, reaproveitada = obter_ce_original(*args, **kwargs)
        medidor.marcar_ce_reaproveitada(reaproveitada)
        return ce, reaproveitada

    principal.obter_ce = obter_ce


def rodar_automacao() -> None:
    global medidor
    from automacoes.anexar.aplicativo.metricas import Medidor

    medidor = Medidor()
    principal = importlib.import_module(os.environ.get("ANEXAR_MODULO_PRINCIPAL") or MODULO_PADRAO)
    # Na Central: o ano do SIGEF escolhido na barra lateral e o Chrome da Central (central.py).
    from automacoes.anexar import central
    central.ligar()
    instalar_na_automacao(principal)
    principal.main()


def main(argumentos: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    os.chdir(caminhos.RAIZ)

    threading.Thread(target=_ler_entrada, daemon=True).start()
    builtins.input = _input_que_sobrou
    interacao.definir_canal(perguntar, avisar)

    modo = (argumentos[0] if argumentos else "automacao").lower()
    emitir("inicio", modo=modo)
    codigo = 0
    try:
        if modo == "automacao":
            rodar_automacao()
        else:
            print(f"Modo desconhecido: {modo}")
            codigo = 2
    except KeyboardInterrupt:
        print("\n⏹️  Parado.")
        codigo = 130
    except Exception as erro:
        # Último recurso: o fluxo já trata os próprios erros; isto pega só o
        # que escapar (ex: falta de uma biblioteca).
        print(f"\n❌ O programa parou: {erro}")
        emitir("erro", titulo=f"O programa parou: {erro}", passos=[])
        codigo = 1
    finally:
        # Um "Parar" que chegue agora não tem mais o que interromper.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        builtins.input = _input_original
        interacao.definir_canal(None, None)
        emitir("fim", codigo=codigo)
    return codigo


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
