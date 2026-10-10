# RSO Santelmo — versão 1.3 — Render Free

Aplicativo Python/Flet para registrar e exportar Relatórios Semanais de Obra.
Inclui quatro abas iniciais, criação de novas obras, tabelas editáveis, cinco dias
de atividades, importação de fotos com legendas, salvamento automático local,
PDF com `fpdf2` e XLSX diagramado com `pandas`/`openpyxl`.

## GitHub e Render

O projeto inclui `render.yaml` para o **plano Free**, servidor web com senha,
backup/restauração em ZIP e workflow de testes do GitHub.
Siga **[DEPLOY.md](DEPLOY.md)** para publicar o conteúdo deste pacote em um
repositório privado e criar o serviço no Render. O Blueprint não adiciona disco ou
banco de dados pago. GitHub guarda o código; Render executa o aplicativo.

No Render Free, os rascunhos e fotos ficam temporariamente em `/tmp/rso-data` e
são perdidos em suspensões, reinícios e novas implantações. **Baixe o backup ZIP**
no botão **Backup e restauração** antes de sair e durante o trabalho. A recuperação
usa o último ZIP baixado; não existe backup automático externo. O navegador precisa
de conexão. A versão desktop continua disponível para trabalho offline.

## Executar

Use **Python 3.10 a 3.13**. A versão do Flet está fixada em **0.28.3**;
não atualize isoladamente para a API 0.8x. Instale em ambiente virtual para evitar
conflito entre o pacote antigo `fpdf` e o `fpdf2`.

```bash
python -m venv .venv
```

Ative o ambiente:

```powershell
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Instale e abra:

```bash
python -m pip install -r requirements.txt
python main.py
```

No Linux, o seletor de arquivos nativo do Flet precisa de `zenity` e de uma sessão
gráfica. Para usar no navegador do mesmo computador:

```bash
python main.py --web --port 8550
```

Abra `http://127.0.0.1:8550`. O servidor escuta somente nesse computador.
Esse modo é destinado a um usuário local; não é um servidor para vários usuários
simultâneos. Use uma única janela de edição por pasta de dados. A instalação e a
preparação inicial do runtime precisam de internet; o modo desktop salva e exporta
sem conexão depois de instalado.

## Uso

1. Escolha a aba da obra. Cada aba tem seu próprio `Report`, controles, fotos e JSON.
2. Preencha a identificação, o período e as condições do tempo. Os nomes dos dias
   acompanham a semana selecionada. Um período parcial é aceito se não houver
   atividades registradas fora dele.
3. Adicione/remova funcionários, equipes terceirizadas e equipamentos. Os totais
   incluem todas as linhas; funcionários próprios e terceiros entram no total geral.
4. Registre as atividades e os materiais (um item por linha). Selecione o **dia das
   novas fotos** antes de importar. Cada dia útil do período precisa de **2 ou 4 fotos**.
   As setas alteram a ordem dentro do mesmo dia. O campo **Dia da foto** permite
   corrigir a classificação, respeitando o limite de quatro no destino.
5. Preencha a assinatura e selecione a geometria do modelo. O tema **verde dos PDFs**
   vem selecionado por padrão, conforme solicitado. O cinza escuro continua opcional.
6. Exporte. No desktop, escolha onde salvar. No navegador, o arquivo abre para
   download; uma cópia também permanece em `exports/` na pasta de dados.

## Regra de fotos por dia

- Segunda a sexta são grupos separados, identificados também no PDF e no Excel.
- **Máximo de quatro fotos por dia.** Uma seleção que exceda o espaço disponível é
  recusada integralmente, sem importar apenas parte dos arquivos.
- Para exportar, cada dia útil incluído no período deve conter **exatamente 2 ou 4
  fotos**. Zero, uma ou três fotos deixam esse dia incompleto; mais de quatro também
  são recusadas pelos exportadores, inclusive se o JSON tiver sido editado manualmente.
- O rascunho pode ficar incompleto, inclusive após remover uma foto. O salvamento
  automático preserva esse estado, e a exportação informa quais dias precisam de ajuste.
- Em um período parcial, somente os dias úteis incluídos exigem fotos. Fotos atribuídas
  a dias fora desse período bloqueiam a exportação até que o período ou a classificação
  seja corrigido. Não há dispensa automática para feriados ou dias sem atividade.
- Rascunhos antigos continuam legíveis. Fotos sem dia são preservadas no grupo
  **Fotos sem dia definido**; o usuário precisa classificá-las antes de exportar.
  Os novos JSONs usam `schema_version: 2`, mantendo leitura da versão 1.

O relatório fotográfico sai em ordem de segunda a sexta, independentemente da ordem
de importação. Uma linha não mistura dias. Quando um grupo continua em outra página,
o título repete o dia, a data, a quantidade total e a indicação de continuação.

Os cadastros iniciais contêm apenas os nomes das obras e a semana corrente. Clientes,
ART, alvará e percentuais históricos **não** são transportados para uma nova semana.
O arquivo de exemplo, separado, reproduz dados históricos da Casa Bosque.

## Persistência e recuperação

Cada alteração recebida pelo aplicativo é salva imediatamente: sem depender do botão
Salvar Rascunho ou do fechamento normal do aplicativo. No desktop, isso funciona
offline; no Render, é necessário que a conexão entregue a alteração ao servidor.
Campos temporariamente incompletos, como uma data em digitação, também são salvos.
A validação completa acontece na exportação. No Render Free, o salvamento automático
é temporário e não substitui o backup ZIP baixado para seu computador.

O diretório padrão é definido por `platformdirs`:

- Windows: `%LOCALAPPDATA%\RSO-Santelmo`.
- Linux: `~/.local/share/RSO-Santelmo`.
- macOS: `~/Library/Application Support/RSO-Santelmo`.

Para escolher outro diretório:

```bash
python main.py --data-dir ./dados-rso
```

A variável `RSO_DATA_DIR` também é aceita. A estrutura é:

```text
dados-rso/
├── drafts/      # UUID.json e UUID.json.bak (versão anterior)
├── media/       # Cópias das fotos, separadas por obra
├── exports/     # Exportações geradas, em diretórios próprios
├── uploads/     # Recepção temporária no modo web
└── public/      # Downloads do modo web; protegidos por senha no servidor publicado
```

Os JSONs usam gravação em arquivo temporário, `fsync` e troca atômica com
`os.replace`. Se um JSON ficar ilegível, o programa tenta recuperar a cópia anterior
e informa o ocorrido. Arquivos com problemas são preservados. Para transportar ou
fazer backup dos dados, copie **toda a pasta**, incluindo `media/`.

Fotos removidas do formulário continuam na pasta de dados para que o backup JSON
permaneça recuperável. As fotos são normalizadas para JPEG, com correção de
orientação EXIF e limite de 2800 pixels no maior lado; os arquivos originais do
usuário permanecem intactos. Cada importação admite até 30 MB. HEIC não é aceito:
converta para JPG/PNG/WebP antes da importação.

## Modelo de exportação e fidelidade

Os quatro PDFs fornecidos estão em `references/`. Foram medidos diretamente:

| Modelo | Margem esquerda | Margem direita (coordenada) | Título, Y | Materiais, Y | Fotos, Y |
|---|---:|---:|---:|---:|---:|
| Átrio / Bosque | 39,00 pt | 556,20 pt | 162,225 pt | 202,65 pt | 318,27 pt |
| Bella Vista | 31,20 pt | 571,60 pt | 150,420 pt | 218,45 pt | 339,68 pt |
| Sintra | 31,20 pt | 571,60 pt | 150,420 pt | 211,85 pt | 333,08 pt |

O papel mede 595,2 × 841,8 pontos, como os anexos. Segunda e terça ocupam a primeira
página; quarta a sexta, materiais e início das fotos, a segunda. As fotos seguintes
ocupam páginas adicionais, sempre respeitando o espaço da assinatura.

O logotipo, a marca d'água, os ícones de sol e os subsets de fontes foram extraídos
dos anexos, preservando transparência. O verde é `#548235`. Os dados fixos da empresa
são exatamente os informados no pedido.

**A exportação é uma adaptação do modelo medido, e não uma cópia pixel a pixel.**
Há diferenças deliberadas para cumprir os requisitos funcionais do pedido:

- Bordas completas nas tabelas e células de dias, em lugar dos círculos e linhas
  parciais dos anexos.
- Uma legenda abaixo de cada foto, em lugar das legendas coletivas acima de grupos.
- Bloco de assinatura em todas as páginas fotográficas e de complemento, em lugar
  de assinatura somente na última página.
- Fotos sem distorção, contidas em áreas fixas; a quantidade de páginas acompanha
  a quantidade de fotos (2 ou 4 por dia) e a escolha de uma ou duas colunas.
- Textos que não caibam até o tamanho mínimo de 8 pt recebem uma referência para
  complemento. Linhas de equipe além das 14 posições do corpo também aparecem no
  complemento e continuam incluídas no total. Nenhum conteúdo é descartado.

Os anexos usam **Tw Cen MT**. Seus subsets cobrem os caracteres originalmente
presentes; o PDF incorpora esses subsets e usa **Noto Sans** para caracteres
adicionais. Para máxima consistência tipográfica em textos novos, aponte para os
arquivos completos de uma instalação licenciada:

```bash
export RSO_FONT_REGULAR=/caminho/TCM_____.TTF
export RSO_FONT_BOLD=/caminho/TCB_____.TTF
```

No PowerShell, use `$env:RSO_FONT_REGULAR = 'C:\caminho\TCM_____.TTF'` e o equivalente
para `RSO_FONT_BOLD`. Para fontes diferentes, o XLSX pode ser ajustado no
`Font(name="Tw Cen MT", ...)` de `excel_generator.py`.

O XLSX tem uma aba diagramada por página, com mesclas, bordas, cores, imagens,
quebra de texto e impressão A4 ajustada a uma página. Uma aba `_Dados`, oculta,
contém os valores numéricos organizados por pandas. O Excel usa a fonte instalada
no computador e seu próprio motor de impressão; pode apresentar pequenas diferenças
de fonte, espaçamento e escala em relação ao PDF. **O PDF é a referência de impressão.**
Alterar células do XLSX não recalcula todos os campos diagramados: para regenerar
totais e paginação, edite o formulário e exporte novamente.

O arquivo denominado Átrio traz “Casa Bella Vista” no campo Obra. Essa inconsistência
não foi propagada para a aba Casa Átrio. Também não foram reproduzidos os subtotais
zerados de alguns anexos: os totais do aplicativo são calculados.

## Código e ajustes

```text
main.py                   Entrada desktop/web local
web.py                    Servidor ASGI para Render
render.yaml               Blueprint Free: serviço, variáveis e armazenamento temporário
DEPLOY.md                 Passo a passo GitHub/Render
rso/web_security.py       Configuração e autenticação HTTP/WebSocket
rso/backup.py             Backup portátil e restauração como novas obras
rso/backup_web.py         Download/upload do ZIP com autenticação
rso/models.py             Report, ResourceRow, Photo e validação
rso/storage.py            JSON atômico, backup e importação de imagens
rso/ui.py                 ObraTab e RSOApp; ft.Tabs, Cards e FilePickers
rso/settings.py           Coordenadas em pontos, paletas e cabeçalho fixo
rso/layout.py             Grade compartilhada, quebra de texto e paginação
rso/pdf_generator.py      PDFGenerator, fpdf2 e border=1
rso/excel_generator.py    ExcelGenerator, pandas, openpyxl e imagens
assets/                   Identidade visual e fontes
examples/                 Dados, fotos e arquivos gerados da Casa Bosque
tools/demo.py             Importação/exportação do exemplo
tests/                    Testes de relatórios, fotos diárias e publicação
.github/workflows/ci.yml   Validação automática no GitHub
```

Para alterar medidas, comece por `Template` e `TEMPLATES` em `settings.py`.
As larguras dos três blocos de mão de obra estão em `LayoutEngine.resources()`;
o grid e os espaços reservados para fotos estão em `LayoutEngine.photo_pages()`.
O mapa de retângulos produzido por `LayoutEngine` é consumido pelos dois geradores.
As coordenadas estão em **pontos**, com origem superior esquerda: 1 mm = 72/25,4 pt.

`ObraTab` herda de `ft.Column`. Isso mantém o encapsulamento sugerido no pedido
sem usar `ft.UserControl`, removido da API desta versão do Flet.

## Exemplo executável e testes

O exemplo parte dos dados e das oito fotos do PDF Casa Bosque, de 28/09/2026 a
02/10/2026. Como o anexo não identifica a data de cada foto, o novo exemplo contém
**12 posições demonstrativas**, distribuídas em **2, 4, 2, 2 e 2 fotos**, com algumas
repetições identificadas nas legendas. As datas atribuídas aos grupos são ilustrativas;
não constituem comprovação de captura ou um novo relatório real da obra.

PDF e XLSX já gerados estão em `examples/gerados/RSO-Demonstracao.pdf` e
`examples/gerados/RSO-Demonstracao.xlsx`. Ambos têm quatro páginas/folhas de impressão.

```bash
python tools/demo.py
python main.py --data-dir ./data-demo
```

O script usa uma pasta separada dos rascunhos normais. Para testes:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
```

Os testes verificam isolamento entre obras, recuperação de JSON, datas e quantidades,
correção EXIF, arquivos ausentes, assinaturas, ausência de sobreposição na grade,
paginação, textos extensos, células numéricas, imagens no XLSX e texto iniciado por
`=` preservado como texto. Também verificam os limites diários nos dois exportadores,
preservação de rascunhos incompletos, leitura de fotos antigas sem dia, agrupamento
cronológico e rejeição de importações/movimentações acima do limite de quatro.
O seletor nativo depende do sistema operacional; os fluxos
web locais são uma alternativa e foram exercitados no navegador durante a entrega.

