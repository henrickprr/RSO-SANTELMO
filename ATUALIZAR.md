# Atualização 1.8.0 — Fixar Informações e Excluir obra

- **Fixar Informações** fica acima do formulário de cada aba. Desmarque para editar
  nome, descrição, cliente, endereço, responsáveis, CREA, ART e alvará. Marque de novo
  para aplicar a correção a essa obra, incluindo os relatórios existentes e futuros.
- O texto em edição é salvo como rascunho, mesmo incompleto. **Cancelar edição**
  restaura o cadastro confirmado. Para exportar, fixe as informações novamente.
- **Excluir obra** pede confirmação com o nome e a quantidade de relatórios. Remove
  todas as semanas da obra selecionada. Cancelar não altera dados. A exclusão fica
  registrada para que as abas antigas não recriem a obra ao salvar ou reiniciar.
- A correção e a exclusão são confirmadas no Firebase quando ele estiver configurado.
  Se estiver indisponível, o aplicativo informa a falha e permite tentar novamente.
- Envie o pacote completo, incluindo o novo arquivo `rso/project_state.py`.
  Não é necessário mudar as regras, as credenciais ou o plano do Firebase.

## Cadastro de obras — recurso preservado

Clique **Adicionar obra**, informe os dados do cabeçalho e da assinatura uma única
vez e clique **Cadastrar obra**. O primeiro relatório abre automaticamente em uma aba.
Para as próximas semanas, use **Novo relatório** e selecione a obra cadastrada.
Os dados permanentes são reaproveitados; os campos semanais começam vazios.

O cadastro é incluído no JSON, no backup e na sincronização do Firebase. Não é
necessário criar coleções ou mudar as regras já usadas pela versão 1.6.0.
Os campos obrigatórios incluem cliente, endereço, responsáveis, CREA, ART e alvará.
Os dados da empresa Santelmo seguem fixos. As quatro obras originais são preservadas.
Envie também o novo arquivo `rso/project_catalog.py`, junto de todo o pacote.

## Firebase Spark — integração preservada

O pacote inclui a integração pronta, mas não contém um projeto ou credencial real.
Siga **[FIREBASE.md](FIREBASE.md)** para criar o projeto Spark, sem faturamento,
e configurar o acesso no Render. Usa Firestore para dados e fotos; não exige Blaze.

- Alterações são salvas no cache e sincronizadas automaticamente após uma breve
  pausa na digitação. O envio também inclui as fotos e legendas.
- O indicador confirma **Salvo no Firebase** somente depois de concluir dados e fotos.
  Falhas e cotas excedidas ficam pendentes e são tentadas novamente.
- Ao reabrir, o app recupera o diário da semana, mesmo com o disco do Render vazio.
- Revisões antigas não substituem silenciosamente outra sessão. Há a opção de
  preservar a edição como uma cópia.
- Novos arquivos: `rso/firebase_backend.py`, `rso/cloud_repository.py`,
  `requirements-firebase.txt`, `firebase.json`, `firestore.rules`,
  `firestore.indexes.json` e `FIREBASE.md`. Envie o pacote completo.

O modo local continua disponível enquanto o Firebase não estiver configurado.
No plano Spark há cotas gratuitas: acompanhe o uso; a configuração não habilita cobrança.

1. Se o aplicativo já tem dados no Render, baixe o backup antes de atualizar.
2. Extraia o ZIP e envie todo o conteúdo para a raiz do repositório GitHub.
   **Preserve as pastas**: `rso/`, `assets/`, `tools/`, `tests/`, `.github/`.
   `web.py`, `render.yaml` e a pasta `rso/` devem estar no mesmo nível.
3. Faça o commit. No Render, use **Manual Deploy → Deploy latest commit**.
   Para ativar a nuvem, configure antes as variáveis e o Secret File descritos em FIREBASE.md.
4. Recarregue o aplicativo com **Ctrl+F5** e restaure o backup, se necessário.
5. Em **Feriados na semana?**, marque **Sim** e preencha **Qual foi o feriado?** ao lado.
6. Exporte o XLSX: todas as seções ficam na aba **RSO**, com assinatura no final.

O Render Free perde os arquivos locais ao reiniciar/publicar. O ZIP do código
não contém os rascunhos que você preencheu: para esta primeira migração, preserve
o backup do aplicativo. Nas atualizações seguintes, o Firebase recupera os dados
já confirmados na nuvem; pendências ainda não sincronizadas dependem do cache.

## Recursos preservados das versões anteriores

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

Para adicionar outro cadastro, use o botão **Adicionar obra**. Para corrigir as
informações de uma obra existente, desmarque **Fixar Informações**, edite e marque novamente.
Não preencha endereços inexistentes nos modelos
com o endereço da empresa: são informações diferentes.

Envie o pacote completo preservando a pasta `rso/`; os arquivos precisam
ser atualizados juntos. O pacote inclui exemplos, documentação e testes de regressão.
`requirements-web.txt` agora inclui o SDK Firebase; o Build Command continua o mesmo.
O serviço permanece no Render Free, sem disco pago.
Os rascunhos existentes são compatíveis; faça backup antes de qualquer deploy.
