# Validação da entrega — versão 1.3 (Render Free)

Verificado em Linux, com Python 3.12, Flet 0.28.3 e fpdf2 2.8.4.

- `python -m pytest -q`: **97 testes aprovados** no ambiente virtual separado,
  instalado somente com `requirements-dev.txt` e suas dependências web.
- `ruff check .`: sem ocorrências.
- `python -m compileall -q main.py web.py rso tools`: concluído.
- `pip check`: nenhuma dependência quebrada.
- Exemplo de agrupamento diário: PDF com **4 páginas e 12 posições fotográficas**,
  XLSX com 4 folhas de impressão e a folha auxiliar oculta. A distribuição é
  **2, 4, 2, 2 e 2 fotos**. Algumas fotos são repetidas e identificadas como demonstração;
  os dias atribuídos não comprovam datas reais de captura.
- Navegador Chromium: troca de abas mantendo clientes distintos, registro de
  atividade e materiais, importação de foto via FilePicker, gravação de legenda,
  salvamento, recuperação ao reabrir, criação de nova obra e exportação dos dois formatos.
- Downloads locais: HTTP 200, tipos de conteúdo PDF/XLSX corretos e bytes iguais
  aos arquivos gerados. O PDF exportado pela interface contém os dados da obra selecionada.
- Layouts Átrio/Bosque, Bella Vista e Sintra: limites de página e ausência de
  sobreposição entre células verificados. Fotos verticais preservam a proporção
  em uma ou duas colunas, com paginação e assinatura.
- Regra diária: zero, uma, três, cinco e seis fotos em um dia impedem os dois tipos
  de exportação; duas e quatro são aceitas. O total semanal não mascara um dia inválido.
- Compatibilidade: fotos de JSONs versão 1 permanecem sem dia, aguardando classificação;
  fotos, caminhos e legendas são preservados. Rascunhos com quantidade ímpar continuam
  sendo salvos e recuperados normalmente.
- Interface: importação acima da capacidade é recusada integralmente, e o dia
  capturado pelo FilePicker não muda ao alterar a seleção ou trabalhar em outra obra.
- Upload web: conclusões concorrentes preservam o dia escolhido; notificações de
  conclusão duplicadas não acrescentam uma foto extra nem ultrapassam o limite.
- Servidor ASGI: `/healthz` público; interface e downloads sem senha retornam 401;
  credenciais inválidas são recusadas; WebSockets de outra origem são bloqueados.
- Uploads assinados exigem autenticação, respeitam o limite de 30 MB e recusam
  assinaturas inválidas/expiradas. Um arquivo parcial acima do limite é removido.
- Configuração: servidor recusa variáveis obrigatórias ausentes ou segredos curtos.
  A gravação sobrevive a novos processos quando a pasta ainda existe; o Render Free
  elimina essa pasta em suspensões/reinícios/deploys, exigindo restauração do backup.
- Blueprint Free: `plan: free`, nenhum disco, `RSO_DATA_DIR=/tmp/rso-data`,
  `RSO_STORAGE_MODE=ephemeral`, deploy automático desligado, porta `$PORT`, um worker.
- Backup e restauração: ZIP com rascunhos incompletos e fotos recupera dias, legendas
  e atividades em outra pasta de dados; as obras existentes são preservadas.
- Backups malformados, fotos inválidas, caminhos com travessia, links simbólicos,
  conteúdo expandido excessivo e uploads acima do limite são recusados. Arquivos
  temporários são removidos; falhas antes da publicação não restauram obras pela metade.
- Download/upload de backup exigem senha, recusam POST de outra origem e usam
  `Cache-Control: private, no-store`. Limite: ZIP de 100 MB, expandido até 200 MB.
- Chromium no modo Free: aviso de dados temporários, abertura da página de backup
  e download real do ZIP conferidos. Após reiniciar com uma pasta vazia (simulando
  a perda do armazenamento), a restauração recuperou os dados e as 12 fotos da
  demonstração; PDF e XLSX voltaram a ser gerados e baixados com sucesso.
- Chromium no novo servidor: autenticação HTTP Basic, interface via WebSocket,
  upload de duas fotos adicionais, legenda, persistência e exportação PDF/XLSX
  aprovados. Downloads autenticados conferidos byte a byte; sem senha retornam 401.

Os testes de publicação foram executados localmente em Linux, usando o servidor
e os comandos preparados para o Render. **Nenhum repositório foi criado no GitHub
e nenhum serviço foi implantado na conta do Render durante esta entrega.**
A implantação real depende de conectar o repositório, definir a senha e criar os
recursos seguindo `DEPLOY.md`. Há avisos de depreciação de bibliotecas nos testes;
não impedem os fluxos validados.

A planilha foi validada com openpyxl; não foi renderizada pelo Microsoft Excel
neste ambiente. Os diálogos nativos de Windows/macOS não foram executados aqui.
As diferenças deliberadas em relação aos modelos e o comportamento das fontes
estão descritos em `README.md`.

