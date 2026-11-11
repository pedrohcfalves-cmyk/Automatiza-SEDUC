"""
Mantido só por compatibilidade: o processo de mentira agora é o
modo_treino.py, na pasta do programa (usado pelo "Modo treino" do
aplicativo e pelos testes). Importar este nome devolve aquele módulo.
"""
import sys

from automacoes.anexar.automacao import modo_treino

sys.modules[__name__] = modo_treino
