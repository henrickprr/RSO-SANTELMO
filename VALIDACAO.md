# Validação — versão 1.5.1

- 94 testes automatizados aprovados, incluindo três novos testes de impressão.
  Lint sem ocorrências.
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
- Exemplo original Casa Bosque: oito fotos, quatro páginas PDF e quatro folhas XLSX.
  As áreas-base de 210 pt em duas colunas e 300 pt em uma coluna recebem agora
  a ampliação final da página, preservando as proporções das imagens.
- Testes de PDF/XLSX cobrem imagens, texto, assinatura, proporções, bordas, paginação,
  fórmulas tratadas como texto, títulos acima das imagens e isolamento das obras.
- Autenticação HTTP/WebSocket, upload, downloads e backups continuam cobertos.
- Render Free continua sem disco pago; os dados locais são temporários e precisam
  de backup ZIP manual. Nenhum deploy remoto foi executado durante esta atualização.

Os testes são locais em Linux/Python 3.12. O XLSX foi verificado com openpyxl;
não foi renderizado no Microsoft Excel. Diferenças tipográficas do modelo estão
explicadas em README.md. Os avisos de depreciação das dependências não impedem
os testes aprovados.
