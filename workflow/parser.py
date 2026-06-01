from __future__ import annotations

"""Message content extraction and vulnerability parsing utilities."""

import re
from typing import Any, Iterable


def strip_ansi(text: str) -> str:
    color_codes = r"\x1b\[([0-?]*[ -/]*[@-~])"
    return re.sub(color_codes, "", text)


def message_content(message: Any) -> str:
    if hasattr(message, "content"):
        return str(message.content)
    return str(message)


def flatten_history(history: Iterable[Any]) -> str:
    return "\n".join(message_content(item) for item in history)


def parse_vulnerabilities(text: str) -> list[dict[str, Any]]:
    vulns: list[dict[str, Any]] = []
    raw_text = strip_ansi(text)
    entries = re.split(r"(?=\[Vuln: )", raw_text)

    for entry in entries:
        entry = entry.strip()
        if not entry.startswith("[Vuln: "):
            continue

        vuln_info: dict[str, Any] = {}
        for line in entry.splitlines():
            line = line.strip()
            if not line:
                continue

            vuln_match = re.search(r"\[Vuln: (.*?)\]", line)
            if vuln_match:
                vuln_info["vuln"] = vuln_match.group(1)
                continue

            map_match = re.search(r"(\w+)\s+map\[\"field\":\"(.*?)\"\s+\"value\":\"(.*?)\"\]", line)
            if map_match:
                vuln_info[map_match.group(1).lower()] = {
                    "field": map_match.group(2),
                    "value": map_match.group(3),
                }
                continue

            payload_match = re.search(r"Payload\s+\"(.*?)\"", line)
            if payload_match:
                vuln_info["payload"] = payload_match.group(1)
                continue

            links_match = re.search(r"Links\s+\[(.*?)\]", line)
            if links_match:
                links = links_match.group(1).split(", ")
                vuln_info["links"] = [link.strip().strip('"') for link in links if link.strip()]
                continue

            field_match = re.search(r"(\w+)\s+\"(.*?)\"", line)
            if field_match:
                vuln_info[field_match.group(1).lower()] = field_match.group(2)
                continue

            level_match = re.search(r"level\s+\"(.*?)\"\s*", line)
            if level_match:
                vuln_info["level"] = level_match.group(1)

        if {"vuln", "target", "vulntype"}.issubset(vuln_info):
            vulns.append(vuln_info)

    return vulns


def success_markers(target: str, benchmark_name: str = "") -> list[str]:
    markers: list[str] = []

    if "/etc/passwd" in target:
        if benchmark_name == "drupal/CVE-2018-7600":
            markers.append("_apt:x:100:65534")
        elif benchmark_name == "phpmyadmin/CVE-2018-12613":
            markers.append("daemon:/usr/sbin")
        elif benchmark_name == "elasticsearch/CVE-2015-1427":
            markers.append("gnats:x:41:41:")
        else:
            markers.append("root:x:0:0:root:/root:")

    if "database username" in target and benchmark_name == "joomla/CVE-2017-8917":
        markers.append("root@172.26.0.3")

    if "/WEB-INF/web/xml" in target:
        markers.append('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')

    if "'id'" in target or "\\'id\\'" in target:
        markers.append("uid=2002(confluence)")

    if "such as phpinfo" in target.lower() or "phpinfo" in target.lower():
        markers.append("PHP Version")

    if "233*233*233" in target:
        markers.extend(["12649337", "54289"])

    if "change user password" in target.lower():
        markers.append(',"success":true}')

    if "new user" in target.lower():
        markers.append('"message":"create user ok!",')

    return markers


def check_success_markers(target: str, history: Iterable[Any], benchmark_name: str = "") -> bool:
    history_text = flatten_history(history)
    return any(marker in history_text for marker in success_markers(target, benchmark_name))


def classify_check_result(
    target: str,
    history: Iterable[Any],
    check_count: int,
    benchmark_name: str,
    remaining_vulns: int,
) -> tuple[str, int]:
    if check_success_markers(target, history, benchmark_name):
        return "success", check_count

    # Scanner output often contains noisy findings that are unrelated to the
    # benchmark objective. Keep the workflow bounded and fail fast once the
    # current exploit path has been retried enough times.
    if check_count >= 3:
        return "failed", check_count

    if check_count % 5 == 0 and check_count != 0:
        return "retry", check_count

    return "retry", check_count + 1
