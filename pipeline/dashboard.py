import time
import requests
import json
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich import box
from datetime import datetime

API_URL  = "http://127.0.0.1:8000"
STORE_ID = "STORE_BLR_002"
REFRESH  = 3  # seconds between updates


def fetch(endpoint):
    try:
        r = requests.get(f"{API_URL}{endpoint}", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def metric_panel(metrics) -> Panel:
    if not metrics:
        return Panel("[red]API unreachable[/red]", title="Metrics")

    visitors    = metrics["unique_visitors"]
    conv_rate   = round(metrics["conversion_rate"] * 100, 1)
    queue       = metrics["queue_depth"]
    abandon     = round(metrics["abandonment_rate"] * 100, 1)

    # Conversion rate colour
    conv_color = "green" if conv_rate >= 20 else "yellow" if conv_rate >= 10 else "red"
    queue_color = "red" if queue >= 10 else "yellow" if queue >= 5 else "green"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Metric", style="dim", width=22)
    table.add_column("Value",  width=16)

    table.add_row("Unique Visitors",   f"[bold]{visitors}[/bold]")
    table.add_row("Conversion Rate",   f"[{conv_color}]{conv_rate}%[/{conv_color}]")
    table.add_row("Queue Depth",       f"[{queue_color}]{queue}[/{queue_color}]")
    table.add_row("Abandonment Rate",  f"[bold]{abandon}%[/bold]")

    # Dwell times
    if metrics.get("avg_dwell_per_zone"):
        table.add_row("", "")
        table.add_row("[dim]Zone Dwell[/dim]", "")
        for zone in metrics["avg_dwell_per_zone"]:
            secs = round(zone["avg_dwell_ms"] / 1000)
            table.add_row(f"  {zone['zone_id']}", f"{secs}s avg")

    return Panel(table, title="[bold]Store Metrics[/bold]", border_style="blue")


def funnel_panel(funnel) -> Panel:
    if not funnel:
        return Panel("[red]No funnel data[/red]", title="Funnel")

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    table.add_column("Stage",     style="dim", width=18)
    table.add_column("Count",     width=8)
    table.add_column("Drop-off",  width=10)
    table.add_column("Visual",    width=20)

    max_count = max((s["count"] for s in funnel["stages"]), default=1) or 1

    for stage in funnel["stages"]:
        count    = stage["count"]
        drop_off = stage["drop_off_pct"]
        bar_len  = int((count / max_count) * 18)
        bar      = "█" * bar_len

        drop_color = "red" if drop_off > 50 else "yellow" if drop_off > 20 else "green"
        drop_str   = f"[{drop_color}]{drop_off}%[/{drop_color}]" if drop_off > 0 else "[dim]—[/dim]"

        table.add_row(stage["stage"], str(count), drop_str, f"[blue]{bar}[/blue]")

    return Panel(table, title="[bold]Conversion Funnel[/bold]", border_style="blue")


def anomaly_panel(anomalies) -> Panel:
    if not anomalies or not anomalies.get("anomalies"):
        return Panel("[green]✓ No active anomalies[/green]",
                     title="[bold]Anomalies[/bold]", border_style="green")

    lines = []
    for a in anomalies["anomalies"]:
        sev = a["severity"]
        color = "red" if sev == "CRITICAL" else "yellow" if sev == "WARN" else "dim"
        icon  = "⚠" if sev in ("CRITICAL", "WARN") else "ℹ"
        lines.append(f"[{color}]{icon} [{sev}][/{color}] {a['description']}")
        lines.append(f"  [dim]→ {a['suggested_action']}[/dim]")
        lines.append("")

    content = "\n".join(lines).strip()
    border  = "red" if any(a["severity"] == "CRITICAL"
                           for a in anomalies["anomalies"]) else "yellow"
    return Panel(content, title="[bold]Anomalies[/bold]", border_style=border)


def heatmap_panel(heatmap) -> Panel:
    if not heatmap or not heatmap.get("zones"):
        return Panel("[dim]No zone data yet[/dim]",
                     title="[bold]Zone Heatmap[/bold]", border_style="blue")

    zones = sorted(heatmap["zones"],
                   key=lambda z: z["normalised_score"], reverse=True)[:8]

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    table.add_column("Zone",       style="dim", width=18)
    table.add_column("Visits",     width=8)
    table.add_column("Dwell",      width=8)
    table.add_column("Heat",       width=22)

    for z in zones:
        score   = z["normalised_score"]
        bar_len = int(score / 5)
        bar     = "█" * bar_len
        color   = "red" if score > 70 else "yellow" if score > 40 else "green"
        secs    = round(z["avg_dwell_ms"] / 1000)
        conf    = "" if z["data_confidence"] == "ok" else " [dim](low data)[/dim]"

        table.add_row(
            z["zone_id"],
            str(int(z["visit_frequency"])),
            f"{secs}s",
            f"[{color}]{bar}[/{color}]{conf}"
        )

    return Panel(table, title="[bold]Zone Heatmap[/bold]", border_style="blue")


def header_panel(health) -> Panel:
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "[green]● API Online[/green]"
    stale  = ""

    if not health:
        status = "[red]● API Offline[/red]"
    elif health.get("stale_feed"):
        stale  = "  [yellow]⚠ STALE FEED[/yellow]"

    last = ""
    if health and health.get("last_event_timestamp"):
        last = f"  Last event: [dim]{health['last_event_timestamp']}[/dim]"

    content = f"{status}{stale}{last}  [dim]Refreshing every {REFRESH}s — {now}[/dim]"
    return Panel(content,
                 title="[bold]Store Intelligence Dashboard — STORE_BLR_002[/bold]",
                 border_style="blue")


def build_layout(console) -> str:
    health    = fetch("/health")
    metrics   = fetch(f"/stores/{STORE_ID}/metrics")
    funnel    = fetch(f"/stores/{STORE_ID}/funnel")
    anomalies = fetch(f"/stores/{STORE_ID}/anomalies")
    heatmap   = fetch(f"/stores/{STORE_ID}/heatmap")

    layout = Layout()
    layout.split_column(
        Layout(header_panel(health),                    name="header", size=3),
        Layout(name="body")
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right")
    )
    layout["left"].split_column(
        Layout(metric_panel(metrics),  name="metrics"),
        Layout(anomaly_panel(anomalies), name="anomalies")
    )
    layout["right"].split_column(
        Layout(funnel_panel(funnel),   name="funnel"),
        Layout(heatmap_panel(heatmap), name="heatmap")
    )
    return layout


def main():
    console = Console()
    console.print("\n[bold blue]Store Intelligence Dashboard[/bold blue]")
    console.print(f"[dim]Connecting to {API_URL} ...[/dim]\n")

    with Live(build_layout(console),
              console=console,
              refresh_per_second=1,
              screen=True) as live:
        while True:
            time.sleep(REFRESH)
            live.update(build_layout(console))


if __name__ == "__main__":
    main()