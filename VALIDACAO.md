# Validação — versão 1.4.1

- Base 1.4: 91 testes automatizados aprovados. Lint da 1.4.1 sem ocorrências.
- Feriados 1.4.1: seleção exclusiva Sim/Não conferida com cliques repetidos,
  gravação/reabertura do rascunho e marcação no layout compartilhado por PDF/XLSX.
- Dados cadastrais das quatro obras conferidos com os PDFs: clientes, responsáveis,
  CREA, ART e alvará. Campos fixos somente para leitura na UI e reaplicados antes
  de salvar/exportar; rascunhos antigos reconhecidos recebem o cadastro atual.
- Endereços das quatro obras e cliente de Átrio editáveis e preservados em JSON/backup.
- Chromium: confirmado o bloqueio dos campos fixos, digitação do endereço de Sintra
  e cliente do Átrio, upload de fotos sem dia e geração de PDF/XLSX pela interface.
- Fotos gerais da semana, sem cabeçalhos de dia/data. Quantidades ímpares aceitas;
  importações acima de quatro fotos permitidas; títulos acima das imagens.
- Exemplo original Casa Bosque: oito fotos, três páginas PDF e três folhas XLSX.
- Testes de PDF/XLSX cobrem imagens, texto, assinatura, proporções, bordas, paginação,
  fórmulas tratadas como texto, títulos acima das imagens e isolamento das obras.
- Autenticação HTTP/WebSocket, upload, downloads e backups continuam cobertos.
- Render Free continua sem disco pago; os dados locais são temporários e precisam
  de backup ZIP manual. Nenhum deploy remoto foi executado durante esta atualização.

Os testes são locais em Linux/Python 3.12. O XLSX foi verificado com openpyxl;
não foi renderizado no Microsoft Excel. Diferenças tipográficas do modelo estão
explicadas em README.md. Os avisos de depreciação das dependências não impedem
os testes aprovados.
