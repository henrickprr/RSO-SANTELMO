# Validação — versão 1.8.0

- 162 testes automatizados aprovados, incluindo 12 com SDK no emulador oficial do
  Firestore Standard v1.22.0. Lint sem ocorrências. Em execução sem emulador, esses
  12 testes de integração são ignorados; os demais 150 continuam executáveis.
- Fixar Informações libera cabeçalho e assinatura; confirmar reaproveita o cadastro
  corrigido em semanas existentes e futuras. Rascunhos parciais sobrevivem ao reinício;
  cancelar a edição preserva as atividades. PDF/XLSX usam cliente e CREA corrigidos.
- Correções das quatro obras originais também são preservadas em backup/restauração.
  A transação do Firestore rejeita uma correção baseada em revisão antiga.
- Exclusão remove todas as semanas da obra, preserva outras obras e fotos locais
  compartilhadas, bloqueia abas antigas e não recria os cadastros após excluir tudo.
- Marcador remoto impede recriação por gravação atrasada; os documentos excluídos
  são removidos. Limpeza interrompida é retomada em nova abertura. Firebase sem conexão
  não produz falsa confirmação de correção ou exclusão; a correção fica recuperável.
- Cancelar o diálogo de exclusão não altera dados. Restaurar um backup anterior
  recupera a obra com outra identidade, sem desfazer o marcador de exclusão.
- Falha na gravação do diário depois de confirmar o cadastro mantém a correção
  recuperável e permite repetir a confirmação sem duplicar a alteração.
- Chromium 1.8.0 com Firestore emulado: desmarcar Fixar Informações, editar cliente,
  recarregar com rascunho preservado, corrigir engenheiro/CREA e fixar novamente.
  Outra semana da mesma obra exportou PDF/XLSX com o cadastro corrigido; o backup
  preservou as atividades. Cancelar a exclusão manteve as abas; confirmar removeu
  as duas semanas selecionadas e preservou Casa Bosque. Com cache vazio, a obra
  excluída não reapareceu nas abas nem em Novo relatório.
- Adicionar obra: cadastro único, rejeição de nomes repetidos (acentos/maiúsculas/espaços),
  submissões simultâneas, isolamento entre semanas e dados permanentes somente para leitura.
- Cadastro novo preservado após reinício local, backup/restauração e recuperação do
  Firestore com diretório do Render vazio. Obras restauradas não se duplicam no seletor.
- PDF e Excel usam o cliente, endereço, responsável técnico, engenheiro, CREA, ART
  e alvará da nova obra. Rascunhos sem o campo de cadastro novo continuam compatíveis.
- Corrigido e coberto por regressão o formulário que mantinha a validação bloqueada
  depois de corrigir campos obrigatórios; Flet limpa o erro usando uma string vazia.
- Chromium 1.7.0: cadastro pela interface, correção de campos obrigatórios, seleção
  automática da nova aba, dados fixos bloqueados e atividade salva no Firestore emulado.
  Servidor reiniciado com cache vazio: cadastro recuperado, nova semana criada pelo
  seletor, cabeçalho/rodapé reutilizados e PDF, XLSX e backup exportados pela interface.
- Firebase Spark: recuperação de relatórios e fotos com cache completamente novo,
  alteração durante envio, retomada da fila, migração de JSONs e restauração de backup.
- Confirmação perdida após commit testada: retry idempotente. Erros de envio/cota
  não indicam salvamento concluído. Cotas simuladas não vazam detalhes da API.
- Fotos maiores que um documento divididas e recuperadas byte a byte; interrupção
  no segundo fragmento não publica manifesto incompleto. Fragmento ausente não
  substitui o arquivo local por download parcial. Fotos iguais são reaproveitadas.
- Transações reais do emulador rejeitam revisão antiga. Concorrência local/entre
  instâncias preserva a edição como cópia. Sessões iniciais não duplicam abas padrão.
- Regras fornecidas rejeitam leitura pública por REST no emulador; o SDK do servidor
  consegue salvar. IAM e credenciais reais ainda dependem do projeto a ser criado.
- Chromium 1.6.0 conectado ao emulador: digitação, duas fotos e legenda salvas sem
  clicar em Salvar. Confirmado o indicador na interface. Servidor encerrado e aberto
  com cache vazio; segunda-feira e hashes das fotos recuperados, sexta acrescentada,
  PDF/XLSX e backup gerados. Conteúdo dos arquivos finais também conferido.
- UI não mostra confirmação antiga de salvamento enquanto ainda recebe fotos do navegador.
- Regressões anteriores continuam cobertas, incluindo persistência, rascunhos antigos,
  impressão condicional e preservação de descrições extensas de feriados.
  Lint sem ocorrências.
- Descrição do feriado preservada na restauração do backup. PDF/XLSX mostram
  o texto apenas quando Sim está selecionado; Não omite a descrição.
- Chromium na versão 1.5.3: campo ao lado de Sim, habilitação/desabilitação,
  preservação ao alternar Sim/Não, isolamento entre obras e recuperação após recarga.
  PDF e XLSX exportados pela interface e conferidos com a descrição preenchida.
- Excel com uma única aba visível RSO, cinco dias em sequência, todas as fotos
  na ordem original, cabeçalho e assinatura únicos. Sem quebras manuais, impressão
  com largura de uma folha e altura livre; a aba auxiliar _Dados permanece oculta.
- Fluxo contínuo conferido nos três modelos, com uma e duas colunas de fotos,
  sem sobreposição entre células, fotos e assinatura. Textos extensos preservados
  no complemento da mesma aba, mesmo quando o plano PDF tem páginas adicionais.
- Falha anterior reproduzida em Chromium: lote de oito fotos importava apenas três
  e deixava o botão bloqueado. A seleção por índices do Flet mudava após cada remoção.
- Chromium na versão 1.5.2: oito fotos enviadas em lote, com nomes, ordem e conteúdo
  conferidos; seleção repetida de `QD.jpeg` em lotes novos e em obras diferentes.
- Falha HTTP 503 simulada: nenhuma foto incompleta adicionada; nova seleção envia
  corretamente e libera o botão. Arquivos temporários removidos ao concluir.
- Testes automatizados de stream já consumido, resultados repetidos, eventos de
  seletores antigos, cancelamento, falha na URL, ordem e isolamento entre obras.
  O erro literal de stream foi simulado no teste; a falha de lote foi reproduzida no navegador.
- PDF e XLSX gerados pela interface após os uploads corrigidos.
- Margens de 7 mm nos quatro lados conferidas nos três modelos de geometria,
  incluindo páginas de fotos e complementos. Sem sobreposição da assinatura.
- PDF de exemplo inspecionado visualmente; textos, desenhos e imagens extraídos
  do arquivo final também conferidos dentro dos limites da área de impressão.
- Chromium na versão 1.5.0: seleção exclusiva Sim/Não, clique repetido na opção já
  selecionada, gravação/reabertura do rascunho e geração de PDF/XLSX pela interface.
  O PDF gerado pelo aplicativo com Sim selecionado foi conferido: Sim marcado e Não vazio.
- Os dois estados de feriados foram conferidos nos arquivos finais: quadrados e
  traços vetoriais no PDF; imagens das caixas e respectivas posições no XLSX.
  Os colchetes com X foram retirados da impressão.
- Títulos das fotos com texto verde em negrito e linhas superior/inferior em
  verde escuro, 1,6 pt no PDF e borda média no Excel. Bordas e cores verificadas
  nos arquivos exportados; PDF também inspecionado visualmente.
- Dados cadastrais das quatro obras conferidos com os PDFs: clientes, responsáveis,
  CREA, ART e alvará. Campos fixos somente para leitura na UI e reaplicados antes
  de salvar/exportar; rascunhos antigos reconhecidos recebem o cadastro atual.
- Endereços das quatro obras e cliente de Átrio editáveis e preservados em JSON/backup.
- Chromium na base 1.4: confirmado o bloqueio dos campos fixos, digitação do endereço de Sintra
  e cliente do Átrio, upload de fotos sem dia e geração de PDF/XLSX pela interface.
- Fotos gerais da semana, sem cabeçalhos de dia/data. Quantidades ímpares aceitas;
  importações acima de quatro fotos permitidas; títulos acima das imagens.
- Exemplo original Casa Bosque: oito fotos, quatro páginas PDF e uma aba contínua XLSX.
  As áreas-base de 210 pt em duas colunas e 300 pt em uma coluna recebem agora
  a ampliação final da página, preservando as proporções das imagens.
- Testes de PDF/XLSX cobrem imagens, texto, assinatura, proporções, bordas, paginação,
  fórmulas tratadas como texto, títulos acima das imagens e isolamento das obras.
- Autenticação HTTP/WebSocket, upload, downloads e backups continuam cobertos.
- Render Free continua sem disco pago. No modo local, os dados dependem de backup;
  no modo Firebase, somente os dados/fotos confirmados na nuvem sobrevivem à perda
  do cache. O pacote não contém projeto ou credenciais reais. Nenhum deploy no Render,
  criação de projeto Firebase ou ativação de faturamento foi executado nesta atualização.

Os testes são locais em Linux/Python 3.12, Firebase Admin 7.7.0 e Firestore SDK 2.34.1.
O emulador não reproduz cobrança, quotas reais ou IAM do projeto. O XLSX foi verificado com openpyxl;
não foi renderizado no Microsoft Excel. Diferenças tipográficas do modelo estão
explicadas em README.md. Os avisos de depreciação das dependências não impedem
os testes aprovados.
