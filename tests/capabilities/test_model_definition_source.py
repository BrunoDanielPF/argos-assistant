import json

import pytest
from pydantic import ValidationError

from assistant.capabilities.model_definition_source import (
    ModelBackedToolDefinitionSource,
)


def metadata_definition() -> dict:
    return {
        "name": "file.metadata.stat",
        "version": "1.0.0",
        "title": "File Metadata",
        "description": "Read creation and modification metadata for one file.",
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
            },
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "path",
                "created_at",
                "modified_at",
                "platform",
                "created_at_reliable",
            ],
            "properties": {
                "path": {"type": "string"},
                "created_at": {"type": ["string", "null"]},
                "modified_at": {"type": "string"},
                "platform": {"type": "string"},
                "created_at_reliable": {"type": "boolean"},
                "explanation": {"type": "string"},
            },
        },
        "permissions": {
            "filesystem": {"read": ["${path}"], "write": []},
            "network": {"enabled": False, "hosts": []},
            "subprocess": {"executables": []},
        },
        "execution": {
            "timeout_seconds": 10,
            "max_output_bytes": 16384,
        },
        "handler_body": (
            "import os\n"
            "import platform\n"
            "from datetime import datetime, timezone\n\n"
            "def run(arguments):\n"
            "    path = os.path.abspath(arguments['path'])\n"
            "    metadata = os.stat(path)\n"
            "    system = platform.system()\n"
            "    reliable = system == 'Windows' or hasattr(metadata, 'st_birthtime')\n"
            "    created = metadata.st_ctime if system == 'Windows' else "
            "getattr(metadata, 'st_birthtime', None)\n"
            "    return {\n"
            "        'path': path,\n"
            "        'created_at': datetime.fromtimestamp(created, timezone.utc).isoformat() "
            "if created is not None else None,\n"
            "        'modified_at': datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat(),\n"
            "        'platform': system,\n"
            "        'created_at_reliable': reliable,\n"
            "        'explanation': '' if reliable else "
            "'Reliable creation time is unavailable on this platform.',\n"
            "    }\n"
        ),
    }


class RecordingStructuredClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def chat_structured(self, messages, schema):
        self.calls.append((messages, schema))
        return {"response": self.response}


def test_model_source_proposes_structured_file_metadata_tool():
    client = RecordingStructuredClient(json.dumps(metadata_definition()))
    source = ModelBackedToolDefinitionSource(client)

    definition = source.build_candidate(
        requested_capability="file.metadata.stat",
        user_goal="quero a data de criacao do arquivo notes.txt",
        arguments={"path": "notes.txt"},
        platform_context={"platform": "win32"},
        original_action={
            "mode": "action",
            "capability": "file.metadata.stat",
            "arguments": {"path": "notes.txt"},
        },
    )

    assert definition is not None
    assert definition.name == "file.metadata.stat"
    assert definition.permissions.filesystem.read == ["${path}"]
    assert definition.permissions.filesystem.write == []
    assert definition.permissions.network.enabled is False
    assert definition.permissions.subprocess.executables == []
    messages, schema = client.calls[0]
    assert schema["additionalProperties"] is False
    assert "structured JSON" in messages[0]["content"]


@pytest.mark.parametrize(
    "response",
    [
        "Here is the tool: " + json.dumps(metadata_definition()),
        '{"name":"file.metadata.stat"}',
    ],
)
def test_model_source_rejects_nonconforming_output(response):
    source = ModelBackedToolDefinitionSource(
        RecordingStructuredClient(response)
    )

    with pytest.raises(ValidationError):
        source.build_candidate(
            requested_capability="file.metadata.stat",
            user_goal="metadata",
            arguments={"path": "notes.txt"},
            platform_context={},
            original_action={},
        )
