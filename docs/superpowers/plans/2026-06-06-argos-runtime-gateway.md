# Argos Runtime and Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar contratos estaveis, observabilidade local e um gateway residente autenticado para que CLI e futuras interfaces compartilhem sessoes e o mesmo runtime do Argos.

**Architecture:** A construcao do agente sai da CLI e passa para `RuntimeFactory`. O `ArgosGateway` expoe uma API HTTP apenas em loopback, autenticada por token local, e mantem um runtime por sessao. A CLI usa `GatewayClient` quando o servico esta disponivel e preserva um modo direto explicito para diagnostico e recuperacao.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, Uvicorn, HTTPX, SQLite, Typer, PyYAML e pytest.

---

## Limites desta entrega

Incluido:

- contratos de requisicao, resposta e eventos;
- fabrica unica do runtime;
- metricas locais sem conteudo de conversa;
- configuracao YAML versionada;
- sessoes persistentes em SQLite;
- gateway local autenticado;
- comandos de processo e diagnostico;
- CLI como cliente do gateway;
- fallback direto explicito.

Nao incluido:

- fila de jobs;
- scheduler;
- voz;
- MCP adicional;
- fine-tuning;
- execucao remota;
- acesso fora de `127.0.0.1`.

## Estrutura de arquivos

```text
src/assistant/
├── runtime/
│   ├── __init__.py
│   ├── contracts.py
│   └── factory.py
├── observability/
│   ├── __init__.py
│   ├── events.py
│   └── metrics.py
├── sessions/
│   ├── __init__.py
│   └── repository.py
├── gateway/
│   ├── __init__.py
│   ├── app.py
│   ├── auth.py
│   ├── client.py
│   ├── process.py
│   └── service.py
├── config.py
└── cli.py
```

## Task 1: contratos do runtime

**Files:**
- Create: `src/assistant/runtime/__init__.py`
- Create: `src/assistant/runtime/contracts.py`
- Test: `tests/runtime/test_contracts.py`

- [ ] **Step 1: escrever os testes dos contratos**

```python
from assistant.runtime.contracts import AgentRequest, AgentResponse


def test_request_generates_run_id_and_keeps_session():
    request = AgentRequest(session_id="default", content="oi")

    assert request.session_id == "default"
    assert request.run_id


def test_response_rejects_unknown_fields():
    try:
        AgentResponse(
            session_id="default",
            run_id="run-1",
            ok=True,
            message="ola",
            suggestions=[],
            unexpected=True,
        )
    except ValueError:
        return
    raise AssertionError("AgentResponse must be strict")
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/runtime/test_contracts.py -q`

Expected: FAIL com `ModuleNotFoundError: assistant.runtime`.

- [ ] **Step 3: implementar modelos estritos**

```python
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    cwd: str | None = None


class AgentResponse(StrictModel):
    session_id: str
    run_id: str
    ok: bool
    message: str
    suggestions: list[dict] = Field(default_factory=list)
```

- [ ] **Step 4: executar os testes**

Run: `python -m pytest tests/runtime/test_contracts.py -q`

Expected: 2 passed.

- [ ] **Step 5: commit**

```bash
git add src/assistant/runtime tests/runtime
git commit -m "feat: add Argos runtime contracts"
```

## Task 2: eventos estruturados e metricas

**Files:**
- Create: `src/assistant/observability/__init__.py`
- Create: `src/assistant/observability/events.py`
- Create: `src/assistant/observability/metrics.py`
- Test: `tests/observability/test_events.py`
- Test: `tests/observability/test_metrics.py`

- [ ] **Step 1: escrever testes de privacidade e duracao**

```python
from assistant.observability.events import EventLog
from assistant.observability.metrics import Timer


def test_event_log_does_not_persist_prompt(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    log.write("request_finished", "s1", "r1", {"duration_ms": 12})

    content = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert "duration_ms" in content
    assert "prompt" not in content


def test_timer_returns_non_negative_duration():
    timer = Timer.start()
    assert timer.elapsed_ms() >= 0
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/observability -q`

Expected: FAIL porque o pacote nao existe.

- [ ] **Step 3: implementar JSONL atomico e timer monotonic**

O evento deve conter apenas:

```python
{
    "timestamp": "ISO-8601 UTC",
    "kind": "request_finished",
    "session_id": "s1",
    "run_id": "r1",
    "details": {"duration_ms": 12},
}
```

`EventLog.write` deve criar o diretorio pai, serializar uma linha JSON e rejeitar as chaves `prompt`, `content`, `token`, `secret` e `password` em `details`.

- [ ] **Step 4: executar os testes**

Run: `python -m pytest tests/observability -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/observability tests/observability
git commit -m "feat: add privacy-safe runtime observability"
```

## Task 3: configuracao YAML versionada

**Files:**
- Modify: `src/assistant/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: escrever testes de precedencia**

```python
def test_config_precedence_is_env_then_yaml_then_default(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "schema_version: '1.0'\nmodel: yaml-model\ngateway_port: 17831\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARGOS_MODEL", "env-model")

    config = AppConfig.load(config_file)

    assert config.model == "env-model"
    assert config.gateway_port == 17831
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL porque `AppConfig.load` nao existe.

- [ ] **Step 3: ampliar `AppConfig`**

Adicionar:

```python
schema_version: Literal["1.0"] = "1.0"
argos_home: Path
gateway_host: Literal["127.0.0.1"] = "127.0.0.1"
gateway_port: int = Field(default=17831, ge=1024, le=65535)
gateway_token_file: Path
gateway_pid_file: Path
gateway_log_file: Path
database_file: Path
event_log_file: Path
direct_mode: bool = False
```

`AppConfig.load(path)` deve aplicar:

```text
variavel de ambiente > YAML > valor padrao
```

Host diferente de `127.0.0.1` deve falhar na validacao nesta fase.

- [ ] **Step 4: executar testes**

Run: `python -m pytest tests/test_config.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/config.py tests/test_config.py
git commit -m "feat: add versioned Argos configuration"
```

## Task 4: fabrica unica do runtime

**Files:**
- Create: `src/assistant/runtime/factory.py`
- Modify: `src/assistant/cli.py`
- Test: `tests/runtime/test_factory.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: testar criacao com sessao injetada**

```python
def test_factory_builds_agent_with_provided_memory(fake_dependencies):
    memory = SessionMemory()
    factory = RuntimeFactory(config=fake_dependencies.config)

    agent = factory.build_agent(memory=memory, confirmer=lambda *_: True)

    assert agent.memory is memory
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/runtime/test_factory.py -q`

Expected: FAIL porque `RuntimeFactory` nao existe.

- [ ] **Step 3: mover a montagem de `build_agent`**

`RuntimeFactory` deve criar:

- `ToolStateStore`;
- `ToolCatalog`;
- `OllamaClient`;
- `Planner`;
- `ActionExecutor`;
- `LongTermMemoryStore`;
- `AssistantAgent`.

A CLI deve manter uma funcao compativel:

```python
def build_agent(confirmer=None) -> AssistantAgent:
    return RuntimeFactory(AppConfig.load()).build_agent(confirmer=confirmer)
```

- [ ] **Step 4: executar regressao**

Run: `python -m pytest tests/runtime/test_factory.py tests/test_cli.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/runtime/factory.py src/assistant/cli.py tests
git commit -m "refactor: centralize Argos runtime construction"
```

## Task 5: repositorio persistente de sessoes

**Files:**
- Create: `src/assistant/sessions/__init__.py`
- Create: `src/assistant/sessions/repository.py`
- Modify: `src/assistant/memory/session.py`
- Test: `tests/sessions/test_repository.py`

- [ ] **Step 1: escrever teste de round-trip**

```python
def test_session_survives_repository_reopen(tmp_path):
    database = tmp_path / "argos.db"
    first = SessionRepository(database)
    memory = SessionMemory()
    memory.add_user_message("conte ate dez")
    first.save("default", memory.snapshot())
    first.close()

    second = SessionRepository(database)
    restored = second.load("default")

    assert restored["history"][0]["content"] == "conte ate dez"
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/sessions/test_repository.py -q`

Expected: FAIL porque `SessionRepository` nao existe.

- [ ] **Step 3: implementar schema SQLite**

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Adicionar `SessionMemory.from_snapshot(snapshot)` para restaurar historico, contexto, auditoria e sugestoes usando os modelos Pydantic existentes.

- [ ] **Step 4: validar persistencia**

Run: `python -m pytest tests/sessions tests/test_session_memory.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/sessions src/assistant/memory/session.py tests
git commit -m "feat: persist Argos sessions in SQLite"
```

## Task 6: autenticacao local do gateway

**Files:**
- Modify: `pyproject.toml`
- Create: `src/assistant/gateway/__init__.py`
- Create: `src/assistant/gateway/auth.py`
- Test: `tests/gateway/test_auth.py`

- [ ] **Step 1: adicionar dependencias**

```toml
"fastapi>=0.115.0",
"uvicorn>=0.34.0",
```

- [ ] **Step 2: escrever testes do token**

```python
def test_token_is_created_once_with_secure_randomness(tmp_path):
    token_file = tmp_path / "gateway.token"
    first = LocalTokenStore(token_file).get_or_create()
    second = LocalTokenStore(token_file).get_or_create()

    assert first == second
    assert len(first) >= 43


def test_invalid_bearer_token_is_rejected(tmp_path):
    store = LocalTokenStore(tmp_path / "gateway.token")
    store.get_or_create()

    assert store.verify("invalid") is False
```

- [ ] **Step 3: executar o teste vermelho**

Run: `python -m pytest tests/gateway/test_auth.py -q`

Expected: FAIL porque `LocalTokenStore` nao existe.

- [ ] **Step 4: implementar token**

Usar `secrets.token_urlsafe(32)` e `hmac.compare_digest`. No Windows, executar `icacls <arquivo> /inheritance:r /grant:r <usuario>:R`; se o comando falhar, o gateway deve recusar inicializacao e informar o caminho. O processo recebe o token em memoria depois da leitura e nunca o escreve em logs.

- [ ] **Step 5: executar os testes**

Run: `python -m pytest tests/gateway/test_auth.py -q`

Expected: todos passam.

- [ ] **Step 6: commit**

```bash
git add pyproject.toml src/assistant/gateway tests/gateway
git commit -m "feat: add local gateway authentication"
```

## Task 7: servico de sessoes do gateway

**Files:**
- Create: `src/assistant/gateway/service.py`
- Test: `tests/gateway/test_service.py`

- [ ] **Step 1: testar reutilizacao da sessao**

```python
def test_service_reuses_and_persists_session(runtime_factory, repository):
    service = GatewayService(runtime_factory, repository)

    first = service.handle(AgentRequest(session_id="s1", content="conte"))
    second = service.handle(AgentRequest(session_id="s1", content="2"))

    assert first.session_id == "s1"
    assert second.session_id == "s1"
    assert repository.load("s1")["history"]
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/gateway/test_service.py -q`

Expected: FAIL porque `GatewayService` nao existe.

- [ ] **Step 3: implementar cache de runtimes**

`GatewayService` deve:

1. carregar snapshot da sessao;
2. criar `SessionMemory.from_snapshot`;
3. construir um agente apenas na primeira chamada da sessao;
4. executar `agent.handle`;
5. persistir snapshot depois da resposta, inclusive em falha controlada;
6. emitir duracao e resultado sem registrar prompt.

Usar um `threading.RLock` por sessao para impedir duas mutacoes simultaneas do mesmo contexto.

- [ ] **Step 4: executar os testes**

Run: `python -m pytest tests/gateway/test_service.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/gateway/service.py tests/gateway/test_service.py
git commit -m "feat: add persistent gateway session service"
```

## Task 8: API local

**Files:**
- Create: `src/assistant/gateway/app.py`
- Test: `tests/gateway/test_app.py`

- [ ] **Step 1: escrever testes HTTP**

```python
def test_health_is_available_with_valid_token(client, token):
    response = client.get(
        "/v1/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_rejects_missing_token(client):
    response = client.post(
        "/v1/chat",
        json={"session_id": "default", "content": "oi"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/gateway/test_app.py -q`

Expected: FAIL porque `create_gateway_app` nao existe.

- [ ] **Step 3: implementar endpoints**

```text
GET  /v1/health
GET  /v1/status
POST /v1/chat
GET  /v1/sessions
GET  /v1/sessions/{session_id}
```

Todos exigem bearer token. `/v1/chat` recebe `AgentRequest` e devolve `AgentResponse`. Erros internos devolvem um `run_id`, mensagem segura e HTTP 500 sem stack trace.

- [ ] **Step 4: executar testes**

Run: `python -m pytest tests/gateway/test_app.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/gateway/app.py tests/gateway/test_app.py
git commit -m "feat: expose authenticated local gateway API"
```

## Task 9: cliente e gerenciamento do processo

**Files:**
- Create: `src/assistant/gateway/client.py`
- Create: `src/assistant/gateway/process.py`
- Test: `tests/gateway/test_client.py`
- Test: `tests/gateway/test_process.py`

- [ ] **Step 1: escrever testes de cliente e PID**

```python
def test_client_sends_token_and_contract(config):
    def handler(request):
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json={
            "session_id": "default",
            "run_id": "r1",
            "ok": True,
            "message": "ola",
            "suggestions": [],
        })

    transport = httpx.MockTransport(handler)
    response = GatewayClient(config, transport=transport).chat("default", "oi")
    assert response.message == "ola"


def test_stale_pid_file_is_removed(tmp_path):
    manager = GatewayProcessManager(pid_file=tmp_path / "gateway.pid")
    manager.pid_file.write_text("999999", encoding="ascii")
    assert manager.status().running is False
    assert not manager.pid_file.exists()
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/gateway/test_client.py tests/gateway/test_process.py -q`

Expected: FAIL porque as classes nao existem.

- [ ] **Step 3: implementar cliente HTTPX**

Timeouts:

```python
httpx.Timeout(connect=2.0, read=120.0, write=10.0, pool=2.0)
```

Mapear conexao recusada para `GatewayUnavailable`, 401 para `GatewayAuthenticationError` e respostas invalidas para `GatewayProtocolError`.

- [ ] **Step 4: implementar processo residente**

Iniciar com:

```text
python -m assistant.gateway.process serve
```

Usar `subprocess.Popen` com `creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS` no Windows, redirecionar stdout/stderr para o log e gravar PID atomicamente. `stop` deve solicitar encerramento gracioso e depois verificar que o PID saiu.

- [ ] **Step 5: executar testes**

Run: `python -m pytest tests/gateway/test_client.py tests/gateway/test_process.py -q`

Expected: todos passam.

- [ ] **Step 6: commit**

```bash
git add src/assistant/gateway/client.py src/assistant/gateway/process.py tests/gateway
git commit -m "feat: manage the resident Argos gateway"
```

## Task 10: comandos CLI e fallback explicito

**Files:**
- Modify: `src/assistant/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: escrever testes dos comandos**

```python
def test_chat_uses_gateway_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(calls),
    )
    result = CliRunner().invoke(app, ["chat", "oi"])
    assert result.exit_code == 0
    assert calls == [("default", "oi")]


def test_chat_direct_bypasses_gateway(monkeypatch):
    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())
    result = CliRunner().invoke(app, ["chat", "--direct", "oi"])
    assert result.exit_code == 0
    assert "Handled oi" in result.stdout
```

- [ ] **Step 2: executar o teste vermelho**

Run: `python -m pytest tests/test_cli.py -q`

Expected: FAIL porque a CLI ainda chama apenas `build_agent`.

- [ ] **Step 3: adicionar comandos**

```text
argos start
argos stop
argos status
argos logs
argos chat "oi"
argos chat --session projeto-x "continue"
argos chat --direct "diagnostico"
argos interactive --session default
```

Se o gateway estiver indisponivel, o modo normal deve orientar `argos start`; ele nao deve cair silenciosamente para modo direto porque isso criaria uma sessao divergente.

- [ ] **Step 4: executar testes**

Run: `python -m pytest tests/test_cli.py -q`

Expected: todos passam.

- [ ] **Step 5: commit**

```bash
git add src/assistant/cli.py tests/test_cli.py
git commit -m "feat: connect Argos CLI to resident gateway"
```

## Task 11: teste de integracao, documentacao e migracao

**Files:**
- Create: `tests/gateway/test_end_to_end.py`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: escrever teste end-to-end**

O teste deve iniciar o app em porta efemera, enviar duas mensagens com o mesmo `session_id`, reconstruir o `GatewayService` com o mesmo SQLite e comprovar que o historico foi restaurado.

- [ ] **Step 2: executar o teste**

Run: `python -m pytest tests/gateway/test_end_to_end.py -q`

Expected: PASS.

- [ ] **Step 3: documentar operacao**

Adicionar ao README:

```text
argos start
argos status
argos
argos stop
```

Documentar `~/.argos/config.yaml`, banco, logs, token, modo `--direct` e troubleshooting de porta ocupada ou Ollama indisponivel.

- [ ] **Step 4: ignorar estado local**

Adicionar ao `.gitignore`:

```gitignore
.argos/
*.db
*.db-shm
*.db-wal
```

- [ ] **Step 5: executar verificacao completa**

Run:

```bash
python -m pip install -e .[dev]
python -m pytest -q
git diff --check
```

Expected:

- toda a suite passa;
- nenhum erro de whitespace;
- CLI atual funciona em modo direto;
- gateway funciona em loopback autenticado.

- [ ] **Step 6: teste manual**

```text
argos start
argos status
argos
argos: quero contar de dois em dois
argos: 2
argos: 4
argos: exit
argos
argos: continue
```

Resultado esperado: a segunda sessao recupera o contexto anterior.

- [ ] **Step 7: commit**

```bash
git add README.md .gitignore tests/gateway/test_end_to_end.py
git commit -m "docs: document resident Argos gateway"
```

## Verificacao final da entrega

- [ ] `python -m pytest -q`
- [ ] `git diff --check`
- [ ] `argos start`
- [ ] `argos status`
- [ ] duas CLIs compartilham a sessao `default`
- [ ] reinicio do gateway preserva a sessao
- [ ] requisicao sem token recebe 401
- [ ] bind fora de `127.0.0.1` e rejeitado
- [ ] logs nao contem prompts, tokens ou secrets
- [ ] `argos stop` encerra o processo e remove PID obsoleto

## Decisoes tecnicas fixadas

1. FastAPI/Uvicorn somente como transporte local; o dominio nao depende do framework.
2. SQLite e o armazenamento inicial para sessoes e sera reutilizado por jobs.
3. O gateway nao sera exposto na rede nesta fase.
4. Nao existe fallback silencioso para modo direto.
5. Conteudo de conversa fica no banco de sessoes, nao nos logs de observabilidade.
6. A CLI continua disponivel como cliente e ferramenta de recuperacao.
7. Nenhuma plataforma externa e dependencia do runtime.
