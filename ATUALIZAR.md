# Atualização 1.5.1 — relatório ampliado e margens menores

1. Se o aplicativo já tem dados no Render, baixe o backup antes de atualizar.
2. Extraia o ZIP e envie todo o conteúdo para a raiz do repositório GitHub.
   **Preserve as pastas**: `rso/`, `assets/`, `tools/`, `tests/`, `.github/`.
   `web.py`, `render.yaml` e a pasta `rso/` devem estar no mesmo nível.
3. Faça o commit. No Render, use **Manual Deploy → Deploy latest commit**.
4. Abra o aplicativo e restaure o backup, se necessário.

O Render Free perde os arquivos locais ao reiniciar/publicar. O ZIP do código
não contém os rascunhos que você preencheu: eles precisam do backup do aplicativo.

## O que mudou

- Margens reduzidas para **7 mm nos quatro lados**, em todas as páginas do PDF
  e do XLSX. Tabelas, títulos, textos, fotos e assinatura aproveitam mais a folha.
  Imagens mantêm suas proporções, sem corte. O exemplo continua com quatro páginas.
- Fotos maiores no PDF e no XLSX, sem corte ou distorção. O relatório acrescenta
  páginas para preservar o rodapé. O exemplo com oito fotos passa de três a quatro páginas.
- Atividades acima das fotos com texto verde em negrito e bordas superior/inferior
  mais espessas em verde escuro, tanto no PDF quanto no XLSX.
- Feriados impressos com caixinhas e marca de seleção, substituindo os colchetes
  com X. A marca acompanha a opção escolhida no aplicativo.
- Feriados na semana com duas caixas, **Sim** e **Não**, permitindo somente uma
  resposta. A seleção fica salva no rascunho e é utilizada nas exportações.
- Cliente, identificação, responsáveis, CREA, ART e alvará fixos por obra,
  preenchidos conforme os PDFs. O cadastro fica em `rso/projects.py`.
- Os endereços e o cliente da Casa Átrio continuam editáveis, conforme autorizado.
- Fotos gerais da semana, sem dia/data, com a atividade acima das imagens.
  Fotos consecutivas com a mesma atividade compartilham o título.
- Novo relatório permite escolher uma obra cadastrada, sem redigitar seu cadastro.
- Rascunhos antigos reconhecidos recebem os dados fixos atuais; campos semanais,
  fotos e as exceções editáveis são preservados.

Para corrigir informações permanentes ou adicionar outro cadastro, altere somente
`rso/projects.py` e publique novamente. Não preencha endereços inexistentes nos modelos
com o endereço da empresa: são informações diferentes.

Esta atualização altera as margens e o layout compartilhado: envie o pacote
completo, mantendo a pasta `rso/`, e não apenas `ui.py`. As dependências e a
configuração do Render Free continuam as mesmas. Os rascunhos existentes são compatíveis.
