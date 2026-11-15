from __future__ import annotations

import argparse
import csv
import json
import sys
import time

from . import __version__
from .scanner import OPEN, parse_ports, resolve, scan
from .services import TOP_PORTS

AVISO = "Use só em máquinas suas ou com autorização por escrito."


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="portscan",
        description="Scanner de portas TCP com threads e captura de banner. " + AVISO,
    )
    p.add_argument("alvo", help="IP ou nome do host")
    p.add_argument("-p", "--portas", help="ex. 22,80,443 ou 1-1024 (padrão, as portas mais comuns)")
    p.add_argument("-t", "--threads", type=int, default=200)
    p.add_argument("--timeout", type=float, default=1.0, help="segundos por porta")
    p.add_argument("--sem-banner", action="store_true", help="não tenta ler o banner do serviço")
    p.add_argument("--todas", action="store_true", help="mostra fechadas e filtradas também")
    p.add_argument("-o", "--saida", help="salva o resultado em .json ou .csv")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def save(path: str, target: str, results) -> None:
    rows = [r.to_dict() for r in results]
    if path.endswith(".csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["port", "state", "service", "banner", "latency_ms"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"alvo": target, "resultados": rows}, fh, ensure_ascii=False, indent=2)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ports = parse_ports(args.portas) if args.portas else TOP_PORTS
        ip = resolve(args.alvo)
    except ValueError as exc:
        print(f"erro, {exc}", file=sys.stderr)
        return 2

    print(f"\n  lince portscan {__version__}")
    print(f"  alvo {args.alvo} ({ip}) com {len(ports)} portas e {args.threads} threads\n")
    print(f"  {'PORTA':<8}{'ESTADO':<11}{'SERVIÇO':<16}BANNER")

    def show(res):
        if res.state == OPEN or args.todas:
            print(f"  {res.port:<8}{res.state:<11}{res.service:<16}{res.banner}")

    started = time.perf_counter()
    results = scan(ip, ports, args.threads, args.timeout, not args.sem_banner, on_result=show)
    total = time.perf_counter() - started
    abertas = sum(r.state == OPEN for r in results)
    print(f"\n  {abertas} aberta(s) em {total:.1f}s")
    if args.saida:
        save(args.saida, args.alvo, results)
        print(f"  resultado salvo em {args.saida}")
    return 0
