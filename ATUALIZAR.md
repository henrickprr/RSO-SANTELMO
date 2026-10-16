# Atualização 1.5.3 — feriado e Excel contínuo

1. Se o aplicativo já tem dados no Render, baixe o backup antes de atualizar.
2. Extraia o ZIP e envie todo o conteúdo para a raiz do repositório GitHub.
   **Preserve as pastas**: `rso/`, `assets/`, `tools/`, `tests/`, `.github/`.
   `web.py`, `render.yaml` e a pasta `rso/` devem estar no mesmo nível.
3. Faça o commit. No Render, use **Manual Deploy → Deploy latest commit**.
4. Recarregue o aplicativo com **Ctrl+F5** e restaure o backup, se necessário.
5. Em **Feriados na semana?**, marque **Sim** e preencha **Qual foi o feriado?** ao lado.
6. Exporte o XLSX: todas as seções ficam na aba **RSO**, com assinatura no final.

O Render Free perde os arquivos locais ao reiniciar/publicar. O ZIP do código
não contém os rascunhos que você preencheu: eles precisam do backup do aplicativo.

## O que mudou

- Excel com uma única aba visível contínua: equipes, cinco dias, materiais, fotos
  e complementos em sequência. Cabeçalho e assinatura aparecem uma vez.
  Sem quebras manuais herdadas do PDF; impressão ajustada a uma folha de largura
  e quantas folhas forem necessárias na altura. A aba auxiliar `_Dados` permanece oculta.
- Campo opcional para descrever o feriado ao lado de Sim. Habilitado quando Sim
  está marcado; a descrição aparece na mesma linha dessa opção no PDF e no XLSX.
- Descrição salva automaticamente por relatório e incluída no backup. Marcar Não
  preserva o texto digitado, mas o retira da impressão. Rascunhos antigos abrem com
  a descrição vazia. Textos extensos usam o complemento para evitar cortes.
- Corrigida a identificação de arquivos em lotes com três ou mais fotos no Flet 0.28.3.
  Cada arquivo agora é enviado ao destino correto e o botão é liberado ao terminar.
- Cada seleção usa um seletor novo; eventos repetidos ou antigos são ignorados,
  evitando reenviar um stream já consumido pelo navegador. Após falha, selecione
  novamente a foto, sem repetir o envio da seleção antiga.
- Importações concluídas são normalizadas na ordem de chegada e ficam isoladas por obra.
- Margens de **7 mm nos quatro lados** das páginas PDF e no contorno da aba Excel.
  Tabelas, títulos, textos, fotos e assinatura aproveitam mais a área disponível.
  Imagens mantêm suas proporções, sem corte. O PDF de exemplo tem quatro páginas.
- Fotos maiores no PDF e no XLSX, sem corte ou distorção. O relatório acrescenta
  páginas PDF para preservar o rodapé. O Excel mantém todas as fotos na mesma aba.
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

Esta atualização altera `rso/models.py`, `rso/ui.py`, `rso/layout.py` e
`rso/excel_generator.py`, além de acrescentar `rso/excel_layout.py`.
Envie o pacote completo preservando a pasta `rso/`; os arquivos precisam
ser atualizados juntos. O pacote inclui exemplos, documentação e testes de regressão.
As dependências e a configuração do Render Free continuam as mesmas.
Os rascunhos existentes são compatíveis; faça backup antes de qualquer deploy.
