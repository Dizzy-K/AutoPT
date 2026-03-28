from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from autort.config.schema import CommandToolProviderConfig, RuntimeConfig, SSHConfig


DEFAULT_MARKER_PREFIX = "__AUTORT_CMD_DONE__"
UNSUPPORTED_MESSAGES = {
    "nano ": "nano is not supported in this environment",
    "searchsploit ": "searchsploit is not supported in this environment",
    "man ": "man is not supported in this environment",
}
NATURAL_LANGUAGE_COMMAND_PREFIXES = (
    "please ",
    "use ",
    "run ",
    "execute ",
    "try ",
    "issue ",
    "send ",
    "command: ",
    "cmd: ",
)
COMMON_SHELL_COMMANDS = {
    "awk",
    "bash",
    "cat",
    "cd",
    "chmod",
    "chown",
    "cp",
    "curl",
    "docker",
    "echo",
    "env",
    "export",
    "find",
    "git",
    "grep",
    "head",
    "id",
    "ls",
    "mkdir",
    "mv",
    "nc",
    "ncat",
    "netcat",
    "nikto",
    "nmap",
    "php",
    "ping",
    "printf",
    "python",
    "python3",
    "rm",
    "sed",
    "sh",
    "sqlmap",
    "tail",
    "touch",
    "uname",
    "wget",
    "whoami",
    "xray",
}


@dataclass(slots=True)
class ShellCommandResult:
    command: str
    output: str
    exit_code: int = 0
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "output": self.output,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


class InteractiveShell:
    """
    Shared command shell adapter.

    Design goals:
    - absorb the useful command-cleaning behavior from legacy implementations
    - remove hardcoded xray fake responses and other test-only branches
    - avoid hardcoded prompt matching by using a command marker
    - support both local execution and delayed SSH connection
    """

    def __init__(
        self,
        config: RuntimeConfig | SSHConfig | None = None,
        *,
        scanner_provider: CommandToolProviderConfig | None = None,
    ) -> None:
        if isinstance(config, RuntimeConfig):
            self.runtime = config
        elif isinstance(config, SSHConfig):
            self.runtime = RuntimeConfig(provider="ssh", ssh=config)
        else:
            self.runtime = RuntimeConfig()
        self.scanner_provider = scanner_provider
        self.client: Any | None = None
        self.session: Any | None = None

    def _uses_ssh(self) -> bool:
        return self.runtime.provider == "ssh"

    def _connect(self) -> None:
        if not self._uses_ssh():
            return
        if self.client is not None and self.session is not None:
            return

        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError(
                "Paramiko is required for InteractiveShell. "
                "Install project dependencies before using the terminal tool."
            ) from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            self.runtime.ssh.host,
            username=self.runtime.ssh.username,
            password=self.runtime.ssh.password,
            port=self.runtime.ssh.port,
            timeout=self.runtime.ssh.timeout,
        )
        self.client = client
        self.session = client.invoke_shell()
        self._drain_pending_output()

    def _drain_pending_output(self, idle_window: float = 0.2) -> None:
        if self.session is None:
            return

        deadline = time.time() + idle_window
        while time.time() < deadline:
            if self.session.recv_ready():
                self.session.recv(4096)
                deadline = time.time() + idle_window
            else:
                time.sleep(0.05)

    def _normalize_command(self, command: str) -> str:
        command = command.strip()

        if command.startswith("```") and command.endswith("```"):
            command = command[3:-3].strip()
            if "\n" in command:
                first_line, _, rest = command.partition("\n")
                if first_line.strip().lower() in {"bash", "sh", "shell", "zsh", "python", "python3"}:
                    command = rest.strip()
        if command.startswith("`") and command.endswith("`"):
            command = command[1:-1].strip()

        if "\n" in command:
            lines = [line.strip() for line in command.splitlines() if line.strip()]
            lines = [line for line in lines if not line.startswith("```")]
            if len(lines) == 1:
                command = lines[0]
            elif lines:
                command = " ".join(lines)

        command = self._strip_natural_language_prefixes(command)

        if self._has_unbalanced_quotes(command):
            command += self._closing_quotes(command)

        for prefix, message in UNSUPPORTED_MESSAGES.items():
            if prefix in command:
                return message

        if "xray" in command and "--poc" in command:
            command = self._remove_xray_poc_argument(command)

        return self._rewrite_scanner_command(command)

    @staticmethod
    def _looks_like_shell_command(command: str) -> bool:
        if not command:
            return False

        if re.search(r"[|&;<>]", command):
            return True

        first_token = command.split()[0].strip().strip("`\"'")
        if first_token in COMMON_SHELL_COMMANDS:
            return True
        if first_token.startswith(("./", "../", "/")):
            return True
        return False

    @classmethod
    def _strip_natural_language_prefixes(cls, command: str) -> str:
        stripped = command.strip()
        for _ in range(3):
            lowered = stripped.lower()
            updated = stripped
            for prefix in NATURAL_LANGUAGE_COMMAND_PREFIXES:
                if not lowered.startswith(prefix):
                    continue
                candidate = stripped[len(prefix) :].strip()
                if cls._looks_like_shell_command(candidate):
                    updated = candidate
                break
            if updated == stripped:
                return stripped
            stripped = updated
        return stripped

    @staticmethod
    def _remove_xray_poc_argument(command: str) -> str:
        parts = command.split()
        kept_parts: list[str] = []
        skip_next = False

        for part in parts:
            if skip_next:
                skip_next = False
                continue
            if part == "--poc":
                skip_next = True
                continue
            kept_parts.append(part)

        return " ".join(kept_parts)

    @staticmethod
    def _has_unbalanced_quotes(command: str) -> bool:
        stack: list[str] = []
        for char in command:
            if char not in {"'", '"'}:
                continue
            if stack and stack[-1] == char:
                stack.pop()
            else:
                stack.append(char)
        return bool(stack)

    @staticmethod
    def _closing_quotes(command: str) -> str:
        stack: list[str] = []
        for char in command:
            if char not in {"'", '"'}:
                continue
            if stack and stack[-1] == char:
                stack.pop()
            else:
                stack.append(char)
        return "".join(reversed(stack))

    def _rewrite_scanner_command(self, command: str) -> str:
        provider = self.scanner_provider
        if provider is None:
            return command

        try:
            parts = shlex.split(command)
        except ValueError:
            return command

        if not parts:
            return command

        first_token = parts[0]
        if Path(first_token).name != "xray" and first_token != "xray":
            return command

        executable = provider.executable.strip() or first_token
        rewritten_parts = self._normalize_scanner_parts([executable, *provider.extra_args, *parts[1:]])
        rewritten_command = shlex.join(rewritten_parts)

        if provider.env:
            env_prefix = " ".join(
                f"{key}={shlex.quote(value)}" for key, value in sorted(provider.env.items())
            )
            rewritten_command = f"{env_prefix} {rewritten_command}"

        if provider.working_directory:
            rewritten_command = (
                f"cd {shlex.quote(provider.working_directory)} && {rewritten_command}"
            )

        return rewritten_command

    @staticmethod
    def _normalize_scanner_parts(parts: list[str]) -> list[str]:
        normalized_parts = list(parts)
        for index, part in enumerate(normalized_parts[:-1]):
            if part != "--url":
                continue
            url = normalized_parts[index + 1].strip()
            if url and "://" not in url:
                normalized_parts[index + 1] = f"http://{url}"
            break
        return normalized_parts

    def _read_until_marker(self, marker: str) -> tuple[str, bool]:
        if self.session is None:
            raise RuntimeError("No session available.")

        start_time = time.time()
        stop_signal_sent = False
        stop_deadline: float | None = None
        output = ""

        while True:
            if self.session.recv_ready():
                output += self.session.recv(8192).decode("utf-8", "ignore")
                if marker in output:
                    return output, stop_signal_sent
            else:
                time.sleep(0.1)

            now = time.time()
            if not stop_signal_sent and now - start_time > self.runtime.ssh.timeout:
                self.session.send("\x03")
                stop_signal_sent = True
                stop_deadline = now + self.runtime.ssh.timeout

            if stop_signal_sent and stop_deadline is not None and now > stop_deadline:
                raise TimeoutError(
                    "Command timeout and could not recover the shell session."
                )

    @staticmethod
    def _extract_exit_code(raw_output: str, marker: str) -> int:
        match = re.search(rf"{re.escape(marker)}:(-?\d+)", raw_output)
        if match:
            return int(match.group(1))
        return 0

    @staticmethod
    def _strip_marker(raw_output: str, marker: str) -> str:
        if marker not in raw_output:
            return raw_output.rstrip()
        prefix, _, _ = raw_output.partition(marker)
        return prefix.rstrip()

    def _trim_output(self, command: str, output: str) -> str:
        lines = output.splitlines()
        if "make" in command:
            return "\n".join(lines[-30:])
        if "configure" in command or "cmake" in command:
            return "\n".join(lines[-20:])
        if "curl" in command and len(output) >= 4000:
            return self._compress_html_output(output)
        return output

    def _compress_html_output(self, output: str) -> str:
        parser = _HTMLTextParser()
        parser.feed(output)
        text = parser.get_text()
        if not text:
            return output[:4000]
        return "Output is too long. Parsed text output:\n" + text[:4000]

    def _execute_ssh(self, normalized_command: str) -> ShellCommandResult:
        self._connect()
        if self.session is None:
            raise RuntimeError("No session available.")

        self._drain_pending_output()

        marker = f"{DEFAULT_MARKER_PREFIX}_{time.time_ns()}__"
        wrapped_command = (
            f"{normalized_command}\n"
            f"printf '\\n{marker}:%s\\n' $?\n"
        )
        self.session.send(wrapped_command)
        raw_output, timed_out = self._read_until_marker(marker)

        exit_code = self._extract_exit_code(raw_output, marker)
        cleaned_output = self._strip_marker(raw_output, marker)
        cleaned_output = self._trim_output(normalized_command, cleaned_output)
        if timed_out:
            cleaned_output = f"{cleaned_output}\nCommand execution timeout!"

        return ShellCommandResult(
            command=normalized_command,
            output=cleaned_output,
            exit_code=exit_code,
            timed_out=timed_out,
        )

    def _execute_local(self, normalized_command: str) -> ShellCommandResult:
        try:
            completed = subprocess.run(
                normalized_command,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.runtime.ssh.timeout,
            )
            output = completed.stdout or ""
            trimmed_output = self._trim_output(normalized_command, output.rstrip())
            return ShellCommandResult(
                command=normalized_command,
                output=trimmed_output,
                exit_code=completed.returncode,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            trimmed_output = self._trim_output(normalized_command, str(output).rstrip())
            if trimmed_output:
                trimmed_output = f"{trimmed_output}\nCommand execution timeout!"
            else:
                trimmed_output = "Command execution timeout!"
            return ShellCommandResult(
                command=normalized_command,
                output=trimmed_output,
                exit_code=124,
                timed_out=True,
            )

    def execute(self, command: str) -> ShellCommandResult:
        normalized_command = self._normalize_command(command)
        if not normalized_command:
            return ShellCommandResult(command=command, output="Empty command.", exit_code=0)

        if normalized_command in UNSUPPORTED_MESSAGES.values():
            return ShellCommandResult(command=command, output=normalized_command, exit_code=0)

        if self._uses_ssh():
            return self._execute_ssh(normalized_command)
        return self._execute_local(normalized_command)

    def execute_command(self, command: str) -> str:
        return self.execute(command).output

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.session = None

    def __enter__(self) -> "InteractiveShell":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
