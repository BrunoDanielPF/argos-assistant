from assistant.intent.router import DeterministicIntentRouter


def test_shell_intent_has_priority_over_file_intents():
    router = DeterministicIntentRouter()

    for message, command in (
        ("rode o comando dir", "dir"),
        ("execute o comando echo teste", "echo teste"),
        ("no terminal rode git status", "git status"),
    ):
        assert router.route(message, context={}) == {
            "mode": "action",
            "capability": "shell.run",
            "arguments": {"command": command},
        }


def test_environment_path_requires_explicit_path_language():
    router = DeterministicIntentRouter()

    assert router.route(
        "adicione C:\\tools ao PATH do Windows",
        context={},
    ) == {
        "mode": "action",
        "capability": "modify_path",
        "arguments": {"value": "C:\\tools", "scope": "user"},
    }
    move = router.route(
        "mova arquivos para uma pasta backup",
        context={"current_cwd": "C:\\work"},
    )
    assert move["capability"] == "file.move_many"
    assert move["arguments"] == {
        "source_root": "C:\\work",
        "pattern": "*",
        "destination": "backup",
    }


def test_file_intents_remain_separate_and_relative():
    router = DeterministicIntentRouter()
    context = {"current_cwd": "C:\\work"}

    assert router.route("crie um arquivo chamado notas.txt", context) == {
        "mode": "action",
        "capability": "create_file",
        "arguments": {"path": "C:\\work\\notas.txt", "content": ""},
    }
    assert router.route("crie uma pasta chamada docs", context) == {
        "mode": "action",
        "capability": "file.create_directory",
        "arguments": {"path": "docs"},
    }
    assert router.route("leia o arquivo notas.txt", context) == {
        "mode": "action",
        "capability": "file.read",
        "arguments": {"path": "notas.txt"},
    }
    assert router.route("abra o arquivo notas.txt", context) == {
        "mode": "action",
        "capability": "file.open",
        "arguments": {"path": "notas.txt"},
    }


def test_search_context_markers_bind_to_operational_cwd():
    router = DeterministicIntentRouter()

    for marker in ("nesta pasta", "aqui", "na pasta atual"):
        plan = router.route(
            f"liste os arquivos txt {marker}",
            {
                "current_cwd": "C:\\runtime",
                "default_search_root": "C:\\fallback",
                "user_home": "C:\\Users\\nome-antigo",
            },
        )
        assert plan["capability"] == "files.search"
        assert plan["arguments"]["root"] == "C:\\runtime"
        assert plan["arguments"]["pattern"] == "*.txt"


def test_delete_simulation_and_real_delete_are_distinct():
    router = DeterministicIntentRouter()
    context = {"current_cwd": "C:\\work"}

    simulated = router.route(
        "simule apagar arquivos .tmp nesta pasta",
        context,
    )
    real = router.route("apague o arquivo lixo.tmp", context)

    assert simulated == {
        "mode": "action",
        "capability": "file.delete_dry_run",
        "arguments": {"path": "C:\\work", "pattern": "*.tmp"},
    }
    assert real == {
        "mode": "action",
        "capability": "file.delete_one",
        "arguments": {"path": "lixo.tmp", "recursive": False},
    }
