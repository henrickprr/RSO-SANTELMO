# RSO Santelmo — versão 1.4.1 — Render Free

Aplicativo Python/Flet para registrar e exportar Relatórios Semanais de Obra.
Inclui quatro abas iniciais, criação de relatórios por obra, tabelas editáveis, cinco dias
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

## Uso e dados fixos por obra

Os dados cadastrais são preenchidos automaticamente pelo arquivo `rso/projects.py`.
Os campos ficam visíveis, mas não podem ser digitados. Cabeçalho da Santelmo,
responsável técnico, engenheiro, CREA, ART, alvará e identificação da obra seguem
os PDFs. ART e alvará são específicos de cada obra, não compartilhados entre elas.

| Obra | Cliente | ART | Alvará |
|---|---|---|---|
| Casa Bella Vista | FRANCISCO E JAMILLE | CE20251725141 | 227/2025 |
| Casa Bosque | DANILO FONSECA | CE20261946083 | 216/2026 |
| Casa Sintra | JUDSON E LAURA | CE20251740545 | 245/2025 |
| Casa Átrio | Editável: não consta no modelo | CE20261896040 | 139/2026 |

Responsável técnico: **ENGº DANILO JOSÉ FONSECA LIMA**. Engenheiro no rodapé:
**DANILO FONSECA**, CREA **1915794803**.

**Exceções autorizadas:** os endereços das quatro obras e o cliente da Casa Átrio
continuam editáveis, pois não constam nos modelos. O endereço do cabeçalho é o da
empresa, não o endereço da obra. Os valores informados nessas exceções são salvos
no rascunho e preservados no backup. Quando preenchido, o endereço acompanha o
campo Obra na exportação; textos longos usam o complemento, sem serem descartados.

1. Escolha a aba da obra ou clique **Novo relatório** e selecione uma obra cadastrada.
2. Preencha período, tempo, feriados e evolução. Em **Feriados na semana?**, marque
   **Sim** ou **Não**; apenas uma caixa permanece selecionada. A resposta é salva
   automaticamente e utilizada no PDF/XLSX. Os dados cadastrais já vêm preenchidos.
3. Ajuste equipes, equipamentos, atividades diárias e chegada de materiais.
4. Adicione as fotos gerais da semana e escreva a **atividade da foto**.
5. Exporte PDF/XLSX. No Render Free, baixe também um backup antes de sair.

Para adicionar outra obra ou corrigir informações permanentes, atualize o cadastro
em `rso/projects.py`. Os novos relatórios começam sem atividades, equipes extras,
fotos ou percentuais históricos. Os rascunhos antigos reconhecidos pelo nome da
obra recebem o cadastro fixo atual, preservando informações semanais e as exceções
editáveis. Os valores antigos do cadastro são substituídos pelos dados dos modelos.
Faça backup antes de atualizar. Rascunhos de obras desconhecidas continuam legíveis.

## Fotografias gerais da semana

As fotos **não são associadas a dias**. Não há seletor de dia, data ou cabeçalho
Segunda/Terça no relatório fotográfico. A regra anterior de 2 ou 4 fotos por dia
foi removida a pedido do usuário. São aceitas quantidades pares ou ímpares, e os
rascunhos/relatórios também podem ser gerados sem fotos.

O nome da atividade aparece **acima das imagens**, em verde. Fotos consecutivas
com o mesmo texto de atividade formam um grupo com título comum; use as setas para
ordená-las. A grade usa uma ou duas colunas e preserva as proporções das imagens.
O título é repetido acima de cada linha de fotos do grupo, inclusive nas continuações.
As atividades escritas no corpo do relatório continuam organizadas por dia da semana.

Fotos de rascunhos antigos mantêm caminhos, títulos e ordem, sem exigir a retirada
manual do antigo campo `day`; ele é ignorado na interface e na exportação. O JSON
continua usando `schema_version: 2`, com leitura da versão 1.

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
- Atividades acima dos grupos de fotos, conforme o pedido atualizado; sem dia/data.
- Bloco de assinatura em todas as páginas fotográficas e de complemento, em lugar
  de assinatura somente na última página.
- Fotos sem distorção, contidas em áreas fixas; a quantidade de páginas acompanha
  a quantidade de fotos da semana e a escolha de uma ou duas colunas.
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
rso/projects.py           Cadastro fixo de cada obra e exceções editáveis
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

O exemplo usa os dados e as **oito fotos originais** do PDF Casa Bosque,
de 28/09/2026 a 02/10/2026, sem duplicações para completar pares por dia.
As atividades aparecem acima dos grupos de imagens. Os arquivos em
`examples/gerados/RSO-Demonstracao.pdf` e `RSO-Demonstracao.xlsx` têm três
páginas/folhas de impressão.

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
`=` preservado como texto. Também verificam cadastro fixo por obra, exceções
editáveis, migração de rascunhos, fotos gerais da semana, título acima das imagens,
quantidades ímpares, uploads concorrentes e backup/restauração.
