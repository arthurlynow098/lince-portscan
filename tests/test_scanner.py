import json
import socket
import threading

import pytest

from portscan.cli import main
from portscan.scanner import CLOSED, OPEN, parse_ports, scan, scan_port


@pytest.fixture
def fake_ssh():
    """Sobe um servidor local que se apresenta como SSH, igual um sshd de verdade."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            conn.sendall(b"SSH-2.0-OpenSSH_9.6 laboratorio\r\n")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield port
    srv.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_parse_ports_mistura_lista_e_intervalo():
    assert parse_ports("80, 22,20-23,22") == [20, 21, 22, 23, 80]


def test_parse_ports_intervalo_invertido():
    assert parse_ports("5-3") == [3, 4, 5]


def test_parse_ports_rejeita_porta_invalida():
    with pytest.raises(ValueError):
        parse_ports("0-10")


def test_porta_aberta_com_banner(fake_ssh):
    res = scan_port("127.0.0.1", fake_ssh, timeout=1)
    assert res.state == OPEN
    assert res.banner.startswith("SSH-2.0-OpenSSH")


def test_porta_fechada():
    # no Windows o RST do loopback demora uns 2s, por isso o timeout maior
    res = scan_port("127.0.0.1", free_port(), timeout=4)
    assert res.state == CLOSED


def test_scan_retorna_ordenado(fake_ssh):
    closed = free_port()
    results = scan("127.0.0.1", [fake_ssh, closed], workers=4, timeout=4)
    assert [r.port for r in results] == sorted([fake_ssh, closed])
    assert {r.port: r.state for r in results}[fake_ssh] == OPEN


def test_cli_salva_json(fake_ssh, tmp_path, capsys):
    out = tmp_path / "res.json"
    code = main(["127.0.0.1", "-p", str(fake_ssh), "-o", str(out)])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["resultados"][0]["state"] == OPEN
    assert "1 aberta(s)" in capsys.readouterr().out
