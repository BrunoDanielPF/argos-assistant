AUTO_EXECUTE = {"open_application", "open_file", "open_url"}
CONFIRM = {"search_files", "run_shell_command", "type_text", "write_file"}
BLOCKED = {"delete_files", "shutdown_system"}


def decide_policy(capability_name: str) -> str:
    if capability_name in AUTO_EXECUTE:
        return "allow"
    if capability_name in CONFIRM:
        return "confirm"
    if capability_name in BLOCKED:
        return "blocked"
    return "confirm"
