"""
Versão do Anexar Documentos -- um lugar só.

O aplicativo mostra esta versão no alto da janela (e na aba "Sobre"), e
cada execução registrada nos relatórios guarda a versão que a gerou --
assim, no estudo sobre a automação, dá para comparar versões diferentes.

Ao lançar uma versão nova: mude VERSAO e DATA_VERSAO aqui e acrescente
o que mudou no CHANGELOG.md.

Esquema (versionamento semântico): MAIOR.MENOR.CORREÇÃO
    MAIOR    -> mudança que quebra o jeito antigo de usar
    MENOR    -> novidade que não quebra nada (ex: o aplicativo)
    CORREÇÃO -> só conserto de erro

Copyright (c) 2026 Pedro Henrique Carpina Farias Alves. Todos os direitos reservados. Ver LICENSE.
"""

NOME_APLICATIVO = "Anexar Documentos"
AUTOR = "Pedro Henrique Carpina Farias Alves"
VERSAO = "1.6.0"
DATA_VERSAO = "2026-10-23"
