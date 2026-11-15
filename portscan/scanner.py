"""Núcleo do scanner.

A ideia é a mesma do "TCP connect scan" do Nmap (-sT). Para cada porta
eu tento completar o three-way handshake. Se conectar, a porta está aberta.
Se o host responder com RST, está fechada. Se nada voltar até o timeout,
considero filtrada (provavelmente tem firewall no caminho).
"""
from __future__ import annotations

import errno
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from .services import HTTP_LIKE, guess

OPEN, CLOSED, FILTERED = "aberta", "fechada", "filtrada"
REFUSED = {errno.ECONNREFUSED, 10061}  # 10061 é o mesmo erro no Windows


@dataclass
class PortResult:
    port: int
    state: str
    service: str
    banner: str = ""
    latency_ms: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ports(spec: str) -> list[int]:
    """Transforma '22,80,8000-8010' em uma lista ordenada e sem repetição."""
    ports: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = (int(x) for x in chunk.split("-", 1))
            if start > end:
                start, end = end, start
            ports.update(range(start, end + 1))
        else:
            ports.add(int(chunk))
    invalid = sorted(p for p in ports if not 1 <= p <= 65535)
    if invalid:
        raise ValueError(f"porta fora do intervalo 1-65535 ({invalid[0]})")
    return sorted(ports)


def resolve(target: str) -> str:
    try:
        return socket.gethostbyname(target)
    except socket.gaierror as exc:
        raise ValueError(f"não consegui resolver o host {target!r}") from exc


def grab_banner(sock: socket.socket, port: int, timeout: float) -> str:
    """Lê o que o serviço manda logo depois da conexão.

    SSH, FTP e SMTP se apresentam sozinhos. Servidor HTTP fica calado
    até receber uma requisição, então nesses eu mando um HEAD simples.
    """
    sock.settimeout(timeout)
    try:
        if port in HTTP_LIKE:
            sock.sendall(b"HEAD / HTTP/1.0\r\nHost: alvo\r\n\r\n")
        data = sock.recv(256)
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace").strip()
    return text.splitlines()[0][:120] if text else ""


def scan_port(ip: str, port: int, timeout: float = 1.0, banner: bool = True) -> PortResult:
    started = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        code = sock.connect_ex((ip, port))
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        if code == 0:
            text = grab_banner(sock, port, timeout) if banner else ""
            return PortResult(port, OPEN, guess(port), text, elapsed)
        if code in REFUSED:
            return PortResult(port, CLOSED, guess(port), latency_ms=elapsed)
        return PortResult(port, FILTERED, guess(port))
    except socket.timeout:
        return PortResult(port, FILTERED, guess(port))
    finally:
        sock.close()


def scan(target: str, ports: list[int], workers: int = 200, timeout: float = 1.0,
         banner: bool = True, on_result=None) -> list[PortResult]:
    """Varre várias portas em paralelo com um pool de threads.

    Threads funcionam bem aqui porque quase todo o tempo é espera de rede,
    e durante essa espera o GIL fica livre.
    """
    ip = resolve(target)
    results: list[PortResult] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(ports)))) as pool:
        futures = [pool.submit(scan_port, ip, p, timeout, banner) for p in ports]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            if on_result:
                on_result(res)
    return sorted(results, key=lambda r: r.port)
