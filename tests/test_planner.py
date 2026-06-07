import pytest
from pathlib import Path

from assistant.planner import Planner, PlannerError


class FailIfCalledClient:
    def chat(self, messages):
        raise AssertionError("LLM should not be called for heuristic route")


class FakeOllamaClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return {
            "response": '{"mode":"action","capability":"open_url","arguments":{"url":"https://ollama.com"}}'
        }


class FakeMalformedClient:
    def __init__(self, response):
        self._response = response

    def chat(self, messages):
        return self._response


def test_planner_parses_structured_action_response():
    llm_client = FakeOllamaClient()
    planner = Planner(llm_client=llm_client, capabilities=["open_application", "open_url"])
    plan = planner.create_plan("open ollama website")

    assert plan["mode"] == "action"
    assert plan["capability"] == "open_url"
    assert plan["arguments"]["url"] == "https://ollama.com"
    assert "Supported capabilities: open_application, open_url." in llm_client.messages[0]["content"]
    assert "You are Argos." in llm_client.messages[0]["content"]
    assert "ordinary informational questions directly" in llm_client.messages[0]["content"]
    assert "Never invent a capability named clarification" in llm_client.messages[0]["content"]


def test_planner_retries_spurious_clarification_for_common_question():
    class SpuriousClarificationClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1
            if self.calls == 1:
                return {
                    "response": (
                        '{"mode":"clarification","question":"Voce quis dizer pao?",'
                        '"pending":{"field":"intention","action":'
                        '{"capability":"clarification","arguments":{}},'
                        '"options":[{"id":"sim","label":"sim"}]}}'
                    )
                }
            return {
                "response": (
                    '{"mode":"answer","content":"Claro. Aqui esta a receita."}'
                )
            }

    client = SpuriousClarificationClient()
    planner = Planner(llm_client=client)

    plan = planner.create_plan("como fazer um pao de forma?")

    assert plan == {
        "mode": "answer",
        "content": "Claro. Aqui esta a receita.",
    }
    assert client.calls == 2


def test_planner_uses_tool_free_fallback_when_clarification_persists():
    class PersistentClarificationClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1
            if self.calls < 3:
                return {
                    "response": (
                        '{"mode":"clarification","question":"Qual contexto?",'
                        '"pending":{"field":"context","action":'
                        '{"capability":"user.project_scaffold","arguments":{}},'
                        '"options":[{"id":"food","label":"comida"}]}}'
                    )
                }
            assert "Do not use tools" in messages[0]["content"]
            return {
                "response": (
                    '{"mode":"answer","content":"Misture os ingredientes e asse."}'
                )
            }

    client = PersistentClarificationClient()
    planner = Planner(
        llm_client=client,
        tool_definitions=[
            {
                "name": "user.project_scaffold",
                "description": "Cria projeto definido pelo usuario.",
                "input_schema": {"type": "object"},
            }
        ],
    )

    plan = planner.create_plan("como fazer um pao de forma?")

    assert plan["mode"] == "answer"
    assert client.calls == 3


def test_planner_keeps_required_clarification_for_executable_request():
    class RequiredClarificationClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1
            return {
                "response": (
                    '{"mode":"clarification","question":"Qual arquivo devo editar?",'
                    '"pending":{"field":"path","action":'
                    '{"capability":"write_file","arguments":{"content":"ola"}},'
                    '"options":[{"id":"informar","label":"informar caminho"}]}}'
                )
            }

    client = RequiredClarificationClient()
    planner = Planner(
        llm_client=client,
        capabilities=["write_file"],
    )

    plan = planner.create_plan("edite um arquivo e escreva ola")

    assert plan["mode"] == "clarification"
    assert plan["pending"]["field"] == "path"
    assert client.calls == 1


def test_planner_accepts_free_text_clarification_without_options():
    class FreeTextClarificationClient:
        def chat(self, messages):
            return {
                "response": (
                    '{"mode":"clarification",'
                    '"question":"Voce esta se referindo a web, mobile ou outro tipo?",'
                    '"pending":{"field":"project_type",'
                    '"action":{"capability":"answer","arguments":{}},'
                    '"accept_free_text":true}}'
                )
            }

    planner = Planner(llm_client=FreeTextClarificationClient())

    plan = planner.create_plan("quais linguagens podemos usar para um site de vendas?")

    assert plan["mode"] == "clarification"
    assert plan["pending"]["field"] == "project_type"
    assert plan["pending"]["options"] == []
    assert plan["pending"]["accept_free_text"] is True


def test_planner_defaults_model_clarification_without_options_to_free_text():
    class MissingOptionsClarificationClient:
        def chat(self, messages):
            return {
                "response": (
                    '{"mode":"clarification",'
                    '"question":"Voce quer web, mobile ou outro tipo?",'
                    '"pending":{"field":"project_type",'
                    '"action":{"capability":"answer","arguments":{}}}}'
                )
            }

    planner = Planner(llm_client=MissingOptionsClarificationClient())

    plan = planner.create_plan("quais linguagens podemos usar para um site de vendas?")

    assert plan["mode"] == "clarification"
    assert plan["pending"]["options"] == []
    assert plan["pending"]["accept_free_text"] is True


def test_planner_preserves_explicit_windows_path_for_file_write():
    class MalformedPathClient:
        def chat(self, messages):
            return {
                "response": (
                    '{"mode":"action","capability":"write_file","arguments":{'
                    '"path":"salve essa receita no arquivo '
                    'C:\\\\Users\\\\frand\\\\AppData\\\\Local\\\\Temp\\\\argos-confirmation-test.md",'
                    '"content":"# Receita\\n\\nMisture os ingredientes.",'
                    '"write_mode":"replace"}}'
                )
            }

    planner = Planner(llm_client=MalformedPathClient())

    plan = planner.create_plan(
        "salve essa receita no arquivo "
        "C:\\Users\\frand\\AppData\\Local\\Temp\\argos-confirmation-test.md"
    )

    assert plan["mode"] == "action"
    assert plan["arguments"]["path"] == (
        "C:\\Users\\frand\\AppData\\Local\\Temp\\argos-confirmation-test.md"
    )
    assert plan["arguments"]["content"].startswith("# Receita")


def test_planner_uses_heuristic_for_open_application():
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan("open calculator")

    assert plan == {
        "mode": "action",
        "capability": "open_application",
        "arguments": {"application": "calculator"},
    }


def test_planner_uses_heuristic_for_open_url():
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan("open https://ollama.com")

    assert plan == {
        "mode": "action",
        "capability": "open_url",
        "arguments": {"url": "https://ollama.com"},
    }


def test_planner_uses_heuristic_for_open_file_path():
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan("open file C:\\Users\\frand\\OneDrive\\Documentos\\model-IA\\README.md")

    assert plan == {
        "mode": "action",
        "capability": "open_file",
        "arguments": {"path": "C:\\Users\\frand\\OneDrive\\Documentos\\model-IA\\README.md"},
    }


def test_planner_uses_heuristic_for_find_file_in_path():
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan("find README.md in C:\\Users\\frand\\OneDrive\\Documentos\\model-IA")

    assert plan == {
        "mode": "action",
        "capability": "search_files",
        "arguments": {
            "root": "C:\\Users\\frand\\OneDrive\\Documentos\\model-IA",
            "pattern": "README.md",
            "max_results": 5,
        },
    }


def test_planner_uses_context_for_find_without_explicit_path():
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan(
        "find README.md",
        context={"default_search_root": "C:\\Users\\frand\\OneDrive\\Documentos\\model-IA"},
    )

    assert plan == {
        "mode": "action",
        "capability": "search_files",
        "arguments": {
            "root": "C:\\Users\\frand\\OneDrive\\Documentos\\model-IA",
            "pattern": "README.md",
            "max_results": 5,
        },
    }


def test_planner_creates_markdown_in_user_home_from_portuguese_request(tmp_path):
    planner = Planner(llm_client=FailIfCalledClient())
    plan = planner.create_plan(
        "vamos criar um markdown na pasta do meu usuario, esse arquivo markdown precisa ter hello world escrito",
        context={"user_home": str(tmp_path)},
    )

    expected_path = Path(tmp_path) / "hello_world.md"
    assert plan == {
        "mode": "plan",
        "steps": [
            {
                "capability": "create_file",
                "arguments": {"path": str(expected_path), "content": "hello world"},
            },
            {
                "capability": "open_file",
                "arguments": {"path": str(expected_path)},
            },
        ],
    }


def test_planner_includes_long_term_memories_in_system_prompt():
    llm_client = FakeOllamaClient()
    planner = Planner(llm_client=llm_client)

    planner.create_plan(
        "como devo responder?",
        context={
            "long_term_memories": [
                {
                    "learning": "O usuario prefere respostas objetivas em portugues.",
                    "context": "preferencias",
                    "source_file": "correcoes.md",
                }
            ]
        },
    )

    system_prompt = llm_client.messages[0]["content"]
    assert "Relevant long-term memories:" in system_prompt
    assert "O usuario prefere respostas objetivas em portugues." in system_prompt


def test_planner_includes_dynamic_tool_schema_in_system_prompt():
    llm_client = FakeOllamaClient()
    planner = Planner(
        llm_client=llm_client,
        tool_definitions=[
            {
                "name": "user.project_scaffold",
                "description": "Cria um projeto definido pelo usuario.",
                "input_schema": {
                    "type": "object",
                    "required": ["name", "directory"],
                },
            }
        ],
    )

    planner.create_plan("crie um backend")

    system_prompt = llm_client.messages[0]["content"]
    assert "user.project_scaffold" in system_prompt
    assert '"required": ["name", "directory"]' in system_prompt


def test_planner_keeps_specific_development_template_as_guidance_without_tool(tmp_path):
    planner = Planner(llm_client=FailIfCalledClient())

    plan = planner.create_plan(
        "quero criar um app backend com java, me ajude estruturando os arquivos iniciais",
        context={"user_home": str(tmp_path)},
    )

    assert plan["mode"] == "answer"
    assert "tool" in plan["content"].lower()
    assert "spring" not in plan["content"].lower()


def test_planner_keeps_generic_project_opening_non_executable():
    planner = Planner(llm_client=FailIfCalledClient())

    plan = planner.create_plan("argos, vamos comecar a desenvolver um projeto")

    assert plan["mode"] == "answer"
    assert "tipo de projeto" in plan["content"].lower()


def test_planner_handles_reminder_request_without_development_tool():
    planner = Planner(llm_client=FailIfCalledClient())

    plan = planner.create_plan(
        "argos me lembre que daqui 10 minutos precisamos criar um documento "
        "para iniciar a especificação de requisitos"
    )

    assert plan["mode"] == "answer"
    assert "lembrete" in plan["content"].lower()
    assert "spring" not in plan["content"].lower()


def test_planner_sends_previous_conversation_to_model():
    llm_client = FakeOllamaClient()
    planner = Planner(llm_client=llm_client)

    planner.create_plan(
        "e 4 + 4?",
        context={
            "conversation_history": [
                {"role": "user", "content": "quanto e 2 + 2?"},
                {"role": "assistant", "content": "2 + 2 = 4"},
            ]
        },
    )

    assert llm_client.messages[1:] == [
        {"role": "user", "content": "quanto e 2 + 2?"},
        {"role": "assistant", "content": "2 + 2 = 4"},
        {"role": "user", "content": "e 4 + 4?"},
    ]


def test_planner_loading_context_wraps_only_llm_call():
    events = []

    class LoadingContext:
        def __enter__(self):
            events.append("loading-start")

        def __exit__(self, exc_type, exc, traceback):
            events.append("loading-stop")

    class RecordingClient:
        def chat(self, messages):
            events.append("llm-call")
            return {"response": '{"mode":"answer","content":"ok"}'}

    planner = Planner(
        llm_client=RecordingClient(),
        loading_context=lambda: LoadingContext(),
    )

    planner.create_plan("oi")

    assert events == ["loading-start", "llm-call", "loading-stop"]


def test_planner_requests_write_mode_for_ambiguous_file_edit():
    planner = Planner(llm_client=FailIfCalledClient())

    plan = planner.create_plan(
        "preciso editar um arquivo hello_world colocando de texto ola mundo bruno nesse arquivo"
    )

    assert plan["mode"] == "clarification"
    assert plan["pending"]["field"] == "write_mode"
    assert plan["pending"]["action"] == {
        "capability": "write_file",
        "arguments": {
            "path": "hello_world",
            "content": "ola mundo bruno",
        },
    }


@pytest.mark.parametrize(
    ("answer", "expected_mode"),
    [
        ("1", "replace"),
        ("pode substituir tudo", "replace"),
        ("adicione no final sem apagar", "append"),
    ],
)
def test_planner_resolves_pending_write_mode_from_natural_answer(answer, expected_mode):
    planner = Planner(llm_client=FailIfCalledClient())
    pending = {
        "field": "write_mode",
        "question": "Voce quer substituir ou adicionar ao final?",
        "action": {
            "capability": "write_file",
            "arguments": {"path": "hello_world", "content": "ola mundo bruno"},
        },
        "options": [
            {"id": "replace", "label": "substituir"},
            {"id": "append", "label": "adicionar ao final"},
            {"id": "cancel", "label": "cancelar"},
        ],
    }

    plan = planner.create_plan(answer, context={"pending_clarification": pending})

    assert plan == {
        "mode": "action",
        "capability": "write_file",
        "arguments": {
            "path": "hello_world",
            "content": "ola mundo bruno",
            "write_mode": expected_mode,
        },
    }


def test_planner_repeats_clarification_when_answer_is_uncertain():
    class UncertainClient:
        def chat(self, messages):
            return {
                "response": (
                    '{"mode":"clarification_response",'
                    '"selection":null,"confidence":0.2}'
                )
            }

    pending = {
        "field": "write_mode",
        "question": "Voce quer substituir ou adicionar ao final?",
        "action": {
            "capability": "write_file",
            "arguments": {"path": "hello_world", "content": "ola mundo bruno"},
        },
        "options": [
            {"id": "replace", "label": "substituir"},
            {"id": "append", "label": "adicionar ao final"},
        ],
    }
    planner = Planner(llm_client=UncertainClient())

    plan = planner.create_plan("nao sei bem", context={"pending_clarification": pending})

    assert plan["mode"] == "clarification"
    assert plan["pending"] == pending


def test_planner_accepts_model_generated_clarification():
    class ClarificationClient:
        def chat(self, messages):
            return {
                "response": (
                    '{"mode":"clarification",'
                    '"question":"Qual arquivo voce quer usar?",'
                    '"pending":{"field":"path",'
                    '"action":{"capability":"write_file","arguments":{'
                    '"content":"novo","write_mode":"replace"}},'
                    '"options":['
                    '{"id":"one","label":"primeiro"},'
                    '{"id":"two","label":"segundo"}]}}'
                )
            }

    planner = Planner(llm_client=ClarificationClient())

    plan = planner.create_plan("edite aquele arquivo")

    assert plan["mode"] == "clarification"
    assert plan["question"] == "Qual arquivo voce quer usar?"
    assert plan["pending"]["field"] == "path"


def test_planner_resolves_file_option_from_extension_description():
    planner = Planner(llm_client=FailIfCalledClient())
    pending = {
        "field": "path",
        "question": "Qual arquivo devo usar?",
        "action": {
            "capability": "write_file",
            "arguments": {"content": "novo", "write_mode": "replace"},
        },
        "options": [
            {"id": "C:\\Users\\frand\\hello_world.md", "label": "C:\\Users\\frand\\hello_world.md"},
            {"id": "C:\\Users\\frand\\hello_world.txt", "label": "C:\\Users\\frand\\hello_world.txt"},
            {"id": "cancel", "label": "cancelar"},
        ],
    }

    plan = planner.create_plan("quero o arquivo markdown", context={"pending_clarification": pending})

    assert plan["arguments"]["path"] == "C:\\Users\\frand\\hello_world.md"


class FakeAlternateActionClient:
    def chat(self, messages):
        return {
            "response": '{"mode":"action","action":"open_url","url":"https://ollama.com"}'
        }


def test_planner_normalizes_alternate_action_shape():
    planner = Planner(llm_client=FakeAlternateActionClient())
    plan = planner.create_plan("open ollama website")

    assert plan == {
        "mode": "action",
        "capability": "open_url",
        "arguments": {"url": "https://ollama.com"},
    }


class FakePlanClient:
    def chat(self, messages):
        return {
            "response": (
                '{"mode":"plan","steps":['
                '{"capability":"create_file","arguments":{"path":"C:\\\\Users\\\\frand\\\\hello.md","content":"hello world"}},'
                '{"capability":"open_file","arguments":{"path":"C:\\\\Users\\\\frand\\\\hello.md"}}'
                ']}'
            )
        }


def test_planner_accepts_structured_multi_step_plan():
    planner = Planner(llm_client=FakePlanClient())
    plan = planner.create_plan("crie um markdown")

    assert plan == {
        "mode": "plan",
        "steps": [
            {
                "capability": "create_file",
                "arguments": {"path": "C:\\Users\\frand\\hello.md", "content": "hello world"},
            },
            {
                "capability": "open_file",
                "arguments": {"path": "C:\\Users\\frand\\hello.md"},
            },
        ],
    }


class FakeNestedActionClient:
    def chat(self, messages):
        return {
            "response": (
                '{"mode":"action","action":{"type":"open_url","url":"https://ollama.com"}}'
            )
        }


def test_planner_normalizes_nested_action_shape():
    planner = Planner(llm_client=FakeNestedActionClient())
    plan = planner.create_plan("open ollama website")

    assert plan == {
        "mode": "action",
        "capability": "open_url",
        "arguments": {"url": "https://ollama.com"},
    }


class FakeAlternateAnswerClient:
    def chat(self, messages):
        return {
            "response": '{"mode":"answer","response":"https://ollama.ai"}'
        }


def test_planner_normalizes_alternate_answer_shape():
    planner = Planner(llm_client=FakeAlternateAnswerClient())
    plan = planner.create_plan("open ollama website")

    assert plan == {
        "mode": "answer",
        "content": "https://ollama.ai",
    }


class FakeAliasedCapabilityClient:
    def chat(self, messages):
        return {
            "response": '{"mode":"action","capability":"open_website","arguments":{"url":"https://ollama.com"}}'
        }


def test_planner_normalizes_capability_aliases():
    planner = Planner(llm_client=FakeAliasedCapabilityClient())
    plan = planner.create_plan("open ollama website")

    assert plan == {
        "mode": "action",
        "capability": "open_url",
        "arguments": {"url": "https://ollama.com"},
    }


class FakeAliasedApplicationCapabilityClient:
    def chat(self, messages):
        return {
            "response": (
                '{"mode":"action","capability":"open_app","arguments":{"application":"calculator"}}'
            )
        }


def test_planner_normalizes_application_capability_alias():
    planner = Planner(llm_client=FakeAliasedApplicationCapabilityClient())
    plan = planner.create_plan("open calculator")

    assert plan == {
        "mode": "action",
        "capability": "open_application",
        "arguments": {"application": "calculator"},
    }


@pytest.mark.parametrize(
    ("response", "error_message"),
    [
        ({"response": "not json"}, "invalid JSON response"),
        ({}, "response['response']"),
    ],
)
def test_planner_rejects_malformed_responses(response, error_message):
    planner = Planner(llm_client=FakeMalformedClient(response))

    with pytest.raises(PlannerError, match=error_message):
        planner.create_plan("open ollama website")


@pytest.mark.parametrize(
    ("response", "error_message"),
    [
        (
            {"response": '{"mode":"action","arguments":{"url":"https://ollama.com"}}'},
            "capability",
        ),
        (
            {"response": '{"mode":"action","capability":"open_url"}'},
            "arguments",
        ),
        (
            {"response": '{"mode":"answer"}'},
            "content",
        ),
    ],
)
def test_planner_rejects_invalid_plan_shapes(response, error_message):
    planner = Planner(llm_client=FakeMalformedClient(response))

    with pytest.raises(PlannerError, match=error_message):
        planner.create_plan("open ollama website")
