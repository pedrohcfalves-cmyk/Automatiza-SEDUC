"""
Compara as duas cópias de etapa_sei2.py (sigef_sei e anexar): o que é idêntico e o que divergiu.

    python testes/ferramentas/comparar_funcoes.py
"""
import ast
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = os.path.join(RAIZ, "automacoes", "sigef_sei", "etapa_sei2.py")
B = os.path.join(RAIZ, "automacoes", "anexar", "automacao", "etapa_sei2.py")


def definicoes(caminho: str) -> dict:
    """nome -> (ast sem posição nem docstring, nº de linhas) das funções e classes do topo do arquivo."""
    with open(caminho, encoding="utf-8") as arquivo:
        arvore = ast.parse(arquivo.read())
    achados = {}
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.ClassDef)):
            achados[no.name] = (ast.dump(no), no.end_lineno - no.lineno + 1)
    return achados


def main() -> None:
    a, b = definicoes(A), definicoes(B)
    comuns = sorted(set(a) & set(b))
    print(f"{'nome':45} {'idêntica':9} {'linhas sigef_sei':>17} {'linhas anexar':>14}")
    for nome in comuns:
        print(f"{nome:45} {'sim' if a[nome][0] == b[nome][0] else 'NÃO':9} {a[nome][1]:>17} {b[nome][1]:>14}")
    identicas = sum(1 for n in comuns if a[n][0] == b[n][0])
    print(f"\nEm comum: {len(comuns)} ({identicas} idênticas, {len(comuns) - identicas} divergentes)")
    print("Só em sigef_sei:", ", ".join(sorted(set(a) - set(b))) or "—")
    print("Só em anexar:   ", ", ".join(sorted(set(b) - set(a))) or "—")


if __name__ == "__main__":
    main()
