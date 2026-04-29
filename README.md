# Disparos — Onodera

Backend Flask que automatiza dois fluxos da Onodera Estética via WhatsApp:

1. **Treinamentos** — recebe inscrições do Tally, dispara confirmação para as unidades, ativa eventos no grupo geral.
2. **Recrutamento** — recebe currículos do Tally, faz ranking automático com GPT, contata candidatos e encaminha aprovados para o grupo dos franqueados.

Tudo orquestrado por um agente OpenAI que conversa com o gestor pelo WhatsApp.

---

## Stack

- **Flask** + **gunicorn** (deploy no Railway)
- **Supabase** (PostgreSQL)
- **OpenAI GPT-4o** (agente + análise de currículos + perfil comportamental)
- **Agile Talk / Onochat** (gateway WhatsApp)
- **Tally Forms** (inscrições)
- **pdfplumber** (extração de texto de currículos PDF)

---

## Estrutura

```
.
├── app.py                      # Webhooks Flask (whatsapp, treinamento, candidatura, comportamental)
├── services/
│   ├── agent.py                # Agente OpenAI com tool calling
│   ├── treinamentos.py         # Lógica de treinamentos (listar, confirmar, ativar)
│   ├── recrutamento.py         # Ranking, contato e encaminhamento de candidatos
│   ├── memoria.py              # Histórico de conversa do gestor
│   ├── tally.py                # Helpers de parsing do payload Tally
│   ├── whatsapp.py             # Cliente Agile Talk
│   └── supabase_client.py      # Cliente Supabase
├── requirements.txt
├── Procfile
└── .env.example
```

---

## Webhooks

| Endpoint                    | Origem            | Função                                            |
|-----------------------------|-------------------|---------------------------------------------------|
| `POST /webhook/whatsapp`    | Agile Talk        | Mensagens do gestor (agente) e SIM/NÃO de unidades |
| `POST /webhook/treinamento` | Tally             | Nova inscrição em treinamento                      |
| `POST /webhook/candidatura` | Tally             | Novo candidato (currículo)                         |
| `POST /webhook/comportamental` | Tally          | Respostas do formulário comportamental             |
| `GET  /health`              | Railway           | Health check                                       |

---

## Tabelas (Supabase)

- `cronograma` — calendário de treinamentos (data, treinamento, tipo, link, grupo)
- `treinamentos` — inscrições recebidas
- `unidades` — unidades e seus telefones responsáveis
- `vagas` — vagas abertas
- `candidatos` — candidatos inscritos + análise de currículo + perfil comportamental
- `historico_gestor` — histórico de conversa com o agente

---

## Fluxos do agente

**Treinamentos**
- "quais os próximos treinamentos?" → `listar_treinamentos`
- "quem está inscrito em DD/MM?" → `buscar_inscritos_por_data`
- "confirmar presença em DD/MM" → `preview_confirmacao` → (gestor confirma) → `confirmar_presenca`
- "ativar treinamento de DD/MM" → `preview_ativacao` → (gestor confirma) → `ativar_treinamento`
- "relatório de DD/MM" → `relatorio_confirmacoes`

**Recrutamento**
- "ranking de candidatos para Consultora" → `ranking_candidatos` (top 5)
- "entra em contato com o candidato ID X" → `contatar_candidato`
- "encaminha o candidato ID X para os franqueados" → `encaminhar_franqueado`

---

## Rodando localmente

```bash
pip install -r requirements.txt
cp .env.example .env
# preencher as variáveis no .env
python app.py
```

A aplicação sobe na porta 5000.

---

## Deploy

O projeto está deployado no Railway. Cada push na `main` faz redeploy automático via Procfile (`gunicorn app:app`).

Variáveis de ambiente são configuradas direto no painel do Railway. Veja `.env.example` para a lista completa.
