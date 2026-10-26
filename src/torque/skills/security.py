"""
Security copilot: spoken answers about what this PC is doing.

Everything here only LOOKS at this machine (listening ports, connections,
processes, the ARP table). It never scans other hosts, kills anything or
changes settings. The data source is a probe object, so tests use a fake.
"""

import ipaddress
import re
import subprocess
from collections import Counter

import psutil

from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult

# Folders legitimate programs rarely run from.
RISKY_PATH = re.compile(
    r"[\\/](?:temp|tmp|downloads|public|\$recycle\.bin)[\\/]"
    r"|[\\/]appdata[\\/]local[\\/]temp[\\/]",
    re.IGNORECASE,
)

# Windows system process names that malware likes to imitate.
SYSTEM_NAMES = {"svchost.exe", "lsass.exe", "csrss.exe", "winlogon.exe", "services.exe", "explorer.exe"}
SYSTEM_PATH = re.compile(r"[\\/]windows[\\/]", re.IGNORECASE)

LOCAL_ONLY = {"127.0.0.1", "::1"}
ANY_ADDRESS = {"0.0.0.0", "::"}


class PsutilProbe:
    """Reads the live state of this computer."""

    @staticmethod
    def _name(pid):

        try:
            return psutil.Process(pid).name()
        except (psutil.Error, TypeError):
            return "unknown"

    def listening_ports(self):
        """[(port, process, reachable_from_network)], one per port."""

        found = {}

        try:
            connections = psutil.net_connections(kind="inet")
        except psutil.Error:
            return []

        for c in connections:

            if c.status != psutil.CONN_LISTEN or not c.laddr:
                continue

            exposed = c.laddr.ip not in LOCAL_ONLY

            found.setdefault(c.laddr.port, (self._name(c.pid), exposed))

        return sorted((port, name, exposed) for port, (name, exposed) in found.items())

    def connections_by_process(self):
        """Counter of process name -> established connections to other hosts."""

        counts = Counter()

        try:
            connections = psutil.net_connections(kind="inet")
        except psutil.Error:
            return counts

        for c in connections:

            if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
                continue

            if c.raddr.ip in LOCAL_ONLY:
                continue

            counts[self._name(c.pid)] += 1

        return counts

    def top_processes(self, by="cpu", count=3):
        """[(name, percent)] busiest first."""

        rows = []

        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):

            info = p.info
            name = info.get("name") or "unknown"

            if name.lower() in ("system idle process", "idle"):
                continue

            value = info.get("cpu_percent" if by == "cpu" else "memory_percent") or 0.0

            rows.append((name, value))

        # cpu_percent needs two samples; the first call returns 0 for everyone.
        if by == "cpu" and not any(v for _, v in rows):
            psutil.cpu_percent(interval=0.4)
            rows = [
                (p.info.get("name") or "unknown", p.cpu_percent(interval=None))
                for p in psutil.process_iter(["name"])
            ]

        merged = Counter()

        for name, value in rows:
            merged[name] += value

        return merged.most_common(count)

    def processes(self):
        """[(name, exe_path)] for everything we are allowed to inspect."""

        found = []

        for p in psutil.process_iter(["name", "exe"]):

            if p.info.get("exe"):
                found.append((p.info.get("name") or "", p.info["exe"]))

        return found

    def network_devices(self):
        """[(ip, mac)] from the ARP table: devices this PC has talked to recently."""

        try:
            output = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=8, check=False
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []

        devices = []

        for line in output.splitlines():

            match = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f]{2}(?:[-:][0-9a-f]{2}){5})\s+dynamic", line, re.I)

            if not match:
                continue

            ip = ipaddress.ip_address(match.group(1))

            if ip.is_multicast or str(ip).endswith(".255"):
                continue

            devices.append((str(ip), match.group(2).lower().replace("-", ":")))

        return devices


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------

def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _join(items):

    items = list(items)

    if len(items) <= 1:
        return "".join(items)

    return ", ".join(items[:-1]) + " and " + items[-1]


def describe_ports(probe) -> str:

    ports = probe.listening_ports()

    if not ports:
        return "Nothing is listening for connections right now."

    exposed = [(p, n) for p, n, open_to_network in ports if open_to_network]
    local = len(ports) - len(exposed)

    if not exposed:
        return f"{_plural(len(ports), 'port')} open, all of them only reachable from this PC. Nothing is exposed to your network."

    shown = _join(f"{n} on port {p}" for p, n in exposed[:4])
    more = len(exposed) - 4

    text = f"{_plural(len(exposed), 'port')} reachable from your network: {shown}"

    if more > 0:
        text += f", and {more} more"

    text += f". {local} others are local only." if local else "."

    return text


def describe_network_use(probe) -> str:

    counts = probe.connections_by_process()

    if not counts:
        return "Nothing is connected to the internet right now."

    top = counts.most_common(4)

    return "Most connections: " + _join(
        f"{name} with {_plural(n, 'connection')}" for name, n in top
    ) + "."


def describe_top(probe, by) -> str:

    top = probe.top_processes(by=by, count=3)

    if not top:
        return "I couldn't read the process list."

    label = "processor" if by == "cpu" else "memory"

    return f"Using the most {label}: " + _join(f"{name}, {value:.0f} percent" for name, value in top) + "."


def find_suspicious(probe):
    """[(name, reason)]. Heuristics only: a lead to check, not a verdict."""

    seen = set()
    findings = []

    for name, path in probe.processes():

        reason = None

        if RISKY_PATH.search(path):
            reason = "running from a temporary or downloads folder"

        elif name.lower() in SYSTEM_NAMES and not SYSTEM_PATH.search(path):
            reason = "has a Windows system name but isn't in the Windows folder"

        if reason and (name, reason) not in seen:
            seen.add((name, reason))
            findings.append((name, reason))

    return findings


def describe_suspicious(probe) -> str:

    findings = find_suspicious(probe)

    if not findings:
        return "I found nothing unusual in the running programs. That's a quick check, not a full malware scan."

    shown = _join(f"{name}, {reason}" for name, reason in findings[:3])

    more = len(findings) - 3

    text = f"{_plural(len(findings), 'program')} worth a look: {shown}"

    if more > 0:
        text += f", and {more} more"

    return text + ". That's not proof of anything bad, just worth checking."


def describe_devices(probe) -> str:

    devices = probe.network_devices()

    if not devices:
        return "I can't see other devices yet. Try again after using the network for a minute."

    return (
        f"I can see {_plural(len(devices), 'device')} your PC has recently talked to on the network. "
        "Check your router's device list for the full picture."
    )


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def build_security_skills(probe=None, watch=None):

    probe = probe or PsutilProbe()

    def speak(function, *args):
        return lambda _: ActionResult(True, function(probe, *args))

    what = r"(?:what(?:'s| is| are)?|which|show me|tell me)"
    pc = r"(?:my |the )?(?:pc|computer|laptop|machine)"
    net = r"(?:my |the )?(?:network|internet|wifi|wi fi|wi-fi|connection)"

    rules = [
        ("open_ports", rf"(?:{what} )?(?:ports (?:are )?open|open ports|(?:is )?listening|(?:check|scan) (?:my )?(?:open )?ports|(?:check|scan) {pc} for open ports)(?: on {pc})?$",
         speak(describe_ports)),
        ("network_use", rf"{what} (?:is )?(?:using|connected to|eating) {net}$|{what} (?:apps|programs) are (?:using|connected to) {net}$|who is {pc} talking to$",
         speak(describe_network_use)),
        ("top_cpu", rf"{what} (?:is )?(?:using|eating|hogging) (?:all )?(?:my |the )?(?:cpu|processor)$|{what} (?:is )?(?:slowing|making) (?:down )?{pc}(?: slow)?$|{what} is slowing down$",
         speak(describe_top, "cpu")),
        ("top_memory", rf"{what} (?:is )?(?:using|eating|hogging) (?:all )?(?:my |the )?(?:ram|memory)$",
         speak(describe_top, "memory")),
        ("suspicious", rf"(?:is )?(?:any|anything|check for|scan for|look for)(?: thing)? suspicious(?: processes| programs| apps| software)?(?: running)?(?: on {pc})?$|(?:scan|check) {pc} for suspicious (?:processes|programs|apps)$|(?:any )?suspicious (?:processes|programs)$",
         speak(describe_suspicious)),
        ("devices", rf"(?:who(?:'s| is)|what devices are) on {net}$|(?:show|list) (?:the )?devices on {net}$",
         speak(describe_devices)),
    ]

    skills = [Skill(name, SAFE, re.compile(pattern), action) for name, pattern, action in rules]

    from torque.security import persistence as p

    skills.append(Skill(
        "explain_process", SAFE,
        re.compile(r"^(?:(?:what(?:'s| is)|explain|tell me about) (?:the )?(?:process |program )(?P<a>[\w-]{2,40}?)(?: exe)?(?: running)?"
                   r"|(?:what(?:'s| is)|explain|tell me about) (?P<b>[\w-]{2,40}) exe"
                   r"|(?:is|are) (?:the )?(?:process )?(?!(?:it|this|that|there|he|she|they|these|those|everything|anything|water|food)\b)(?P<c>[\w-]{2,40}?)(?: exe)? (?:process )?(?:safe|legit|legitimate|a virus|malware|dangerous|suspicious))$"),
        lambda m: ActionResult(True, p.explain_process(probe, m.group("a") or m.group("b") or m.group("c"))),
        lambda m: ActionResult(True, p.explain_process(probe, m.group("proc"))),
    ))

    if watch is not None:
        skills.append(Skill("startup_check", SAFE, re.compile(
            rf"(?:what(?:'s| is)|check|list|show me) (?:in )?(?:my )?(?:startup|start up|boot|autorun)(?: programs| items| apps| list| entries)?(?: on {pc})?$|(?:what|which) (?:programs |apps )?(?:start|launch|run) (?:with|when|at) (?:my )?(?:{pc}|windows) (?:starts|boots|start up|startup)?$|anything new (?:in|on) (?:my )?startup$"),
            lambda _: ActionResult(True, p.describe_startup(watch))))
        skills.append(Skill("hosts_check", SAFE, re.compile(
            r"(?:has |was |is )?(?:my )?hosts file (?:been )?(?:changed|modified|tampered(?: with)?|ok|okay|safe)?$|(?:check|scan) (?:my )?hosts file$"),
            lambda _: ActionResult(True, p.describe_hosts(watch))))

    return skills
