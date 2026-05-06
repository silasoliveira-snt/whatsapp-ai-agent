# Assistente de IA via WhatsApp — Gestão de Treinamentos e Recrutamento

> Backend em Python/Flask que orquestra um agente conversacional GPT-4o sobre WhatsApp para automatizar dois processos críticos de uma rede de franquias do setor de estética: **gestão de treinamentos** (online e presenciais) e **triagem de currículos para recrutamento**.

Primeiro projeto desenvolvido **100% do zero**, em produção, com impacto direto em duas áreas operacionais distintas.

---

## Sobre o projeto

A operação enfrentava dois gargalos crônicos resolvidos manualmente: coordenar treinamentos contínuos para múltiplas unidades e triar dezenas de currículos para vagas abertas nas franquias. Ambos consumiam horas semanais do gestor e geravam erros recorrentes.

A solução é um único ponto de entrada — o WhatsApp que o gestor já usava — onde uma camada de IA interpreta linguagem natural, decide quais ações executar, mostra preview do impacto antes de qualquer disparo em massa e só então executa após confirmação humana.

### Problemas reais resolvidos

**Treinamentos**
- **Gestão de treinamentos online:** cronograma centralizado, inscrições recebidas via formulário externo persistidas automaticamente, consultas em segundos via WhatsApp.
- **Gestão de treinamentos presenciais:** confirmação de presença orquestrada com responsáveis de cada unidade, captura automática de respostas SIM/NÃO, relatórios consolidados.
- **Ativação de treinamentos via WhatsApp:** divulgação no grupo geral da rede com mensagem customizável por treinamento, disparada com um único comando.

**Recrutamento**
- **Aumento de captação de currículos:** formulário público integrado com persistência automática e match automático com a vaga.
- **Triagem em duas etapas:** primeira etapa por IA (análise do currículo em PDF, nota de 0 a 10 e justificativa); segunda etapa por avaliação comportamental automatizada (perfil psicológico gerado por GPT a partir das respostas).
- **Contato com candidatos por um comando:** "contata o candidato X" dispara WhatsApp pessoal com link da próxima etapa, atualiza status no banco e impede contato duplicado por concorrência.

---

## Demonstração de uso

```
Gestor:  "confirma presença do treinamento do dia 15.05"
Bot:     [preview com todas as unidades e inscritos que receberão a mensagem]
Gestor:  "pode enviar"
Bot:     [dispara mensagens para cada responsável de unidade]

Unidades respondem SIM/NÃO → o sistema captura e atualiza o banco automaticamente.

Gestor:  "relatório do 15.05"
Bot:     ✓ Confirmados (14)  ✗ Recusados (2)  ○ Sem resposta (3)
```

---

## Stack e decisões técnicas

| Camada | Tecnologia | Por que |
|---|---|---|
| Backend | **Python 3.11 + Flask** | Webhooks simples, ecossistema maduro, deploy direto em PaaS |
| LLM | **OpenAI GPT-4o** | Function calling confiável para orquestração determinística |
| Banco | **Supabase (PostgreSQL)** | SDK pronto, dashboard visual, free tier suficiente para a operação |
| Mensageria | **Agile Talk / Onochat** | Gateway oficial WhatsApp Business já contratado pelo cliente |
| Formulários | **Tally Forms** | Webhooks nativos, suporte a upload de PDF, free tier |
| PDF | **pdfplumber** | Extração de texto de currículos para análise por LLM |
| Hospedagem | **Railway** | Deploy contínuo via Git, logs em tempo real |

### Padrões de engenharia aplicados

- **Tool calling forçado** (`tool_choice="required"`): o LLM não responde texto livre — toda resposta passa por uma das 15 ferramentas registradas, tornando a saída auditável e estruturada.
- **Pattern Preview → Confirm → Action:** ações destrutivas ou de disparo em massa exigem visualização prévia e confirmação explícita do gestor. Elimina disparos acidentais.
- **Update atômico** (`UPDATE ... WHERE status != X`): impede contato duplicado em condições de corrida sem precisar de locks.
- **Rollback automático em falhas de envio:** se o WhatsApp falha, o status no banco volta ao estado anterior — coerência garantida entre banco e mensageria.
- **Soft delete reversível:** nada é apagado fisicamente; tool dedicada permite reativar registros arquivados por engano.
- **Cache de extração de PDF:** texto do currículo é extraído uma vez e persistido — re-análises não re-baixam o arquivo.
- **Análise em background com threading:** quando 10+ candidaturas chegam para a mesma vaga, a análise por IA roda em thread daemon sem bloquear o webhook.
- **Memória conversacional persistida:** os últimos 20 turnos da conversa são recarregados a cada nova mensagem, permitindo contexto entre turnos.

---

## Arquitetura

```
WhatsApp ──┐
           ├─▶ Agile Talk ──webhook──▶ Flask App ──┬─▶ OpenAI (GPT-4o)
Tally ─────┘                                       ├─▶ Supabase (Postgres)
                                                   └─▶ Agile Talk (envio)
```

5 webhooks expostos:

- `POST /webhook/whatsapp` — mensagens do gestor + capturas SIM/NÃO de unidades
- `POST /webhook/treinamento` — inscrições recebidas do Tally
- `POST /webhook/candidatura` — currículos recebidos do Tally
- `POST /webhook/comportamental` — respostas do formulário de avaliação
- `GET /health` — healthcheck

15 ferramentas no agente, distribuídas entre: consultas de cronograma, fluxos de confirmação de presença, ativação de treinamentos, ranking e contato de candidatos, e gestão de registros (arquivar/reativar).

---

## Estrutura do código

```
.
├── app.py                          # Webhooks Flask
├── services/
│   ├── agent.py                    # Orquestrador LLM + 15 tools
│   ├── treinamentos.py             # Lógica de treinamentos
│   ├── recrutamento.py             # Análise e pipeline de candidatos
│   ├── memoria.py                  # Histórico de conversa
│   ├── tally.py                    # Parser de payload Tally
│   ├── whatsapp.py                 # Cliente Agile Talk
│   ├── supabase_client.py          # Cliente Supabase
│   └── constants.py                # Constantes e status
├── requirements.txt
└── Procfile
```

---

## Modelo de dados

Seis tabelas no Supabase: `cronograma`, `treinamentos`, `unidades`, `vagas`, `candidatos`, `historico_gestor`. Todas com `arquivado boolean` para soft delete; pipeline de candidatos rastreado por campo `status` em máquina de estados (`novo → analisado → contatado → comportamental_recebido → encaminhado`).

---

## Rodando localmente

```bash
pip install -r requirements.txt
cp .env.example .env
# preencher OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY, AGILE_*, etc.
python app.py
```

Aplicação sobe na porta 5000.

---

## Deploy

Hospedado em Railway. Cada push na `main` dispara redeploy automático via Procfile (`gunicorn app:app`). Variáveis de ambiente gerenciadas pelo painel do Railway.

---

## Aprendizados

Como primeiro projeto desenvolvido integralmente do zero — da modelagem do banco ao deploy em produção — alguns pontos que ficaram como aprendizado central:

- **Confiabilidade > sofisticação:** padrões simples (preview obrigatório, soft delete, update atômico) entregam mais valor operacional do que features avançadas.
- **LLM como orquestrador, não como executor:** deixar o GPT decidir *qual* ação tomar e o código executar *como* — separação que torna o sistema auditável e testável.
- **Webhooks são contratos:** documentar e tratar formatos do Tally, Agile Talk e respostas SIM/NÃO de unidades exigiu lógica defensiva em cada parser.
- **Reversibilidade vale mais que velocidade:** soft delete e rollback automático evitaram retrabalho real em produção.

---

## Status

Em produção, em uso diário pelo gestor.
