#!/usr/bin/env python
"""
Dataverse OptionSet Helper – Rich CLI
======================================
Interactive command-line interface for managing Dataverse OptionSets.

Usage
-----
    python cli.py                          # interactive menu
    python cli.py create-global            # create a global OptionSet
    python cli.py insert --from-csv data.csv --optionset cap_phoneprefix
    python cli.py list-global              # list all global OptionSets
    python cli.py search --label "phone"   # search by label
    python cli.py bulk-insert  --from-csv data.csv --optionset cap_phoneprefix
    python cli.py bulk-update  --from-csv data.csv --optionset cap_phoneprefix
    python cli.py bulk-delete  --from-csv data.csv --optionset cap_phoneprefix
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text
from rich import box

from OptionSetHelper import (
    BatchReport,
    DataverseOptionSetService,
    OptionItem,
    create_service_from_env,
)

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_options_from_csv(path: str) -> list[OptionItem]:
    """
    Load options from a CSV file.

    Supported CSV formats
    ---------------------
    * **2 columns** – ``label, value``  (value must be an integer)
    * **3 columns** – ``col1, col2, value``  → label = "col2 - col1" (same
      concat logic as the notebook)

    The file may have a header row – the loader auto-detects it.
    """
    items: list[OptionItem] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample)
        except csv.Error:
            dialect = csv.excel  # type: ignore[assignment]
        has_header = sniffer.has_header(sample)
        reader = csv.reader(fh, dialect)
        if has_header:
            next(reader)  # skip header
        for row in reader:
            if not row:
                continue
            row = [c.strip() for c in row]
            if len(row) >= 3:
                # col0=sap, col1=value (label text), col2=numeric value
                try:
                    val = int(row[0])
                    label = row[1]
                except ValueError:
                    try:
                        val = int(row[2])
                        label = row[1]
                    except ValueError:
                        continue
                items.append(OptionItem(label=label, value=val))
            elif len(row) == 2:
                label = row[0]
                try:
                    val = int(row[1])
                except ValueError:
                    continue
                items.append(OptionItem(label=label, value=val))
            elif len(row) == 1:
                # single-column: auto-assign value
                items.append(OptionItem(label=row[0], value=len(items)))
    return items


def _load_options_from_json(path: str) -> list[OptionItem]:
    """
    Load options from a JSON file.

    Expected shape: ``[{"label": "...", "value": 1}, ...]``
    or a dict like ``{"Label Text": intValue, ...}``
    """
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    items: list[OptionItem] = []
    if isinstance(data, list):
        for entry in data:
            items.append(OptionItem(label=entry["label"], value=int(entry["value"])))
    elif isinstance(data, dict):
        for label, value in data.items():
            items.append(OptionItem(label=label, value=int(value)))
    return items


def load_options(path: str) -> list[OptionItem]:
    """Auto-detect CSV or JSON and load OptionItems."""
    ext = Path(path).suffix.lower()
    if ext == ".json":
        return _load_options_from_json(path)
    return _load_options_from_csv(path)


def _print_batch_report(report: BatchReport) -> None:
    """Pretty-print a BatchReport with a Rich table."""
    table = Table(
        title="Batch Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=5)
    table.add_column("Label", min_width=20)
    table.add_column("Value", justify="right", width=8)
    table.add_column("Status", justify="center", width=6)
    table.add_column("Result", min_width=12)
    table.add_column("Detail", style="dim")

    for r in report.results:
        status_style = "green" if r.success else "bold red"
        status_icon = "✅" if r.success else "❌"
        table.add_row(
            str(r.index + 1),
            r.label,
            str(r.value),
            Text(str(r.status_code), style=status_style),
            status_icon,
            r.detail,
        )

    console.print(table)
    summary_style = "green" if report.failed == 0 else "yellow"
    console.print(
        Panel(
            f"[bold]Total:[/bold] {report.total}   "
            f"[green]Succeeded:[/green] {report.succeeded}   "
            f"[red]Failed:[/red] {report.failed}",
            title="Summary",
            style=summary_style,
        )
    )


def _print_optionset_table(options: list[dict], language_code: int = 1033) -> None:
    """Print existing OptionSet options in a Rich table."""
    table = Table(title="OptionSet Options", box=box.ROUNDED, show_lines=True)
    table.add_column("Value", justify="right", width=8)
    table.add_column("Label", min_width=30)

    for opt in sorted(options, key=lambda o: o.get("Value", 0)):
        lbl = ""
        for loc in opt.get("Label", {}).get("LocalizedLabels", []):
            if loc.get("LanguageCode") == language_code:
                lbl = loc["Label"]
                break
        table.add_row(str(opt.get("Value", "?")), lbl)

    console.print(table)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_list_global(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """List all global OptionSets."""
    with console.status("[bold cyan]Fetching global OptionSets …"):
        sets = svc.list_global_optionsets()

    table = Table(title="Global OptionSets", box=box.ROUNDED, show_lines=True)
    table.add_column("Name", min_width=30)
    table.add_column("Display Label", min_width=30)
    table.add_column("Type", width=12)
    table.add_column("# Options", justify="right", width=10)

    lang = getattr(args, "language_code", 1033)
    for s in sorted(sets, key=lambda x: x.get("Name", "")):
        display = ""
        for lbl in s.get("DisplayName", {}).get("LocalizedLabels", []):
            if lbl.get("LanguageCode") == lang:
                display = lbl["Label"]
                break
        n_opts = len(s.get("Options", []))
        table.add_row(
            s.get("Name", ""),
            display,
            s.get("OptionSetType", ""),
            str(n_opts),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(sets)} global OptionSets[/dim]")


def cmd_search(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Search global OptionSets by display label."""
    search_text = args.label or Prompt.ask("Search text (display label)")
    lang = getattr(args, "language_code", 1033)

    with console.status(f"[bold cyan]Searching for '{search_text}' …"):
        results = svc.search_global_optionsets_by_label(search_text, lang)

    if not results:
        console.print(f"[yellow]No OptionSets matching '{search_text}'[/yellow]")
        return

    table = Table(title=f"Search Results for '{search_text}'", box=box.ROUNDED)
    table.add_column("Name")
    table.add_column("Display Label")
    table.add_column("# Options", justify="right")

    for s in results:
        display = ""
        for lbl in s.get("DisplayName", {}).get("LocalizedLabels", []):
            if lbl.get("LanguageCode") == lang:
                display = lbl["Label"]
        table.add_row(s["Name"], display, str(len(s.get("Options", []))))

    console.print(table)


def cmd_show(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Show options of a specific OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name")
    entity = getattr(args, "entity", None)
    attribute = getattr(args, "attribute", None)
    lang = getattr(args, "language_code", 1033)

    with console.status(f"[bold cyan]Fetching options for '{name}' …"):
        options = svc.get_optionset_options(
            name,
            entity_logical_name=entity,
            attribute_logical_name=attribute,
        )

    if not options:
        console.print(f"[yellow]OptionSet '{name}' not found or has no options.[/yellow]")
        return

    _print_optionset_table(options, lang)
    console.print(f"\n[dim]Total options: {len(options)}[/dim]")


def cmd_create_global(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Create a new global OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name (e.g. new_phoneprefix)")
    display_label = args.display_label or Prompt.ask("Display label")
    lang = getattr(args, "language_code", 1033)

    # Check if it already exists
    with console.status(f"[bold cyan]Checking if '{name}' exists …"):
        existing = svc.get_global_optionset(name)
    if existing:
        console.print(f"[bold red]OptionSet '{name}' already exists![/bold red]")
        if not Confirm.ask("Continue anyway? (this will fail at the API level)"):
            return

    options: list[OptionItem] = []
    if args.from_file:
        options = load_options(args.from_file)
        console.print(f"Loaded [bold]{len(options)}[/bold] options from {args.from_file}")
    else:
        console.print("[dim]Enter options one by one. Type 'done' to finish.[/dim]")
        while True:
            label = Prompt.ask("  Label (or 'done')")
            if label.lower() == "done":
                break
            value = IntPrompt.ask("  Value")
            options.append(OptionItem(label=label, value=value))

    if not options:
        console.print("[yellow]No options provided – aborting.[/yellow]")
        return

    with console.status(f"[bold cyan]Creating global OptionSet '{name}' …"):
        resp = svc.create_global_optionset(name, display_label, options, lang)

    console.print(
        f"[bold green]✅ Created global OptionSet '{name}' "
        f"({len(options)} options) – HTTP {resp.status_code}[/bold green]"
    )


def cmd_bulk_insert(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Bulk insert options into an existing OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name")
    entity = getattr(args, "entity", None)
    attribute = getattr(args, "attribute", None)
    lang = getattr(args, "language_code", 1033)
    safe = getattr(args, "safe", True)

    if not args.from_file:
        console.print("[red]--from-csv / --from-json is required for bulk insert[/red]")
        return

    options = load_options(args.from_file)
    console.print(f"Loaded [bold]{len(options)}[/bold] options from {args.from_file}")

    BATCH_SIZE = 50
    total = len(options)
    all_results = []
    failed = 0
    succeeded = 0
    from OptionSetHelper import BatchReport
    try:
        from tqdm import tqdm
    except ImportError:
        console.print("[yellow]tqdm not installed. Please install tqdm for progress bars.[/yellow]")
        tqdm = None

    batch_indices = list(range(0, total, BATCH_SIZE))
    use_tqdm = tqdm is not None
    if use_tqdm:
        pbar = tqdm(total=len(batch_indices), desc="Bulk inserting", unit="batch")

    def _cb(msg: str) -> None:
        pass

    import datetime
    for idx, i in enumerate(batch_indices):
        batch = options[i:i+BATCH_SIZE]
        start_dt = datetime.datetime.now()
        ts = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"[dim]Batch starting at {ts}[/dim]")
        # Refresh token at each batch
        try:
            svc.get_bearer_token()
        except Exception as exc:
            console.print(f"[bold red]Token refresh failed: {exc}[/bold red]")
            break
        if safe:
            report, skipped = svc.safe_bulk_insert(
                batch,
                name,
                lang,
                entity_logical_name=entity,
                attribute_logical_name=attribute,
                continue_on_error=args.continue_on_error,
                progress_callback=_cb,
            )
            if skipped:
                console.print(f"[yellow]⚠  Skipped {len(skipped)} duplicate option(s)[/yellow]")
            # Only extend results if report is not None
            if report is not None:
                all_results.extend(report.results)
                failed += report.failed
                succeeded += report.succeeded
        else:
            report = svc.bulk_insert_options(
                batch,
                name,
                lang,
                entity_logical_name=entity,
                attribute_logical_name=attribute,
                continue_on_error=args.continue_on_error,
                progress_callback=_cb,
            )
            all_results.extend(report.results)
            failed += report.failed
            succeeded += report.succeeded
        end_dt = datetime.datetime.now()
        duration = (end_dt - start_dt).total_seconds()
        console.print(f"[dim]Batch finished at {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (duration: {duration:.2f} seconds)[/dim]")
        if use_tqdm:
            pbar.update(1)
    if use_tqdm:
        pbar.close()

    # Compose a single BatchReport for all batches
    final_report = BatchReport(
        results=all_results,
        total=total,
        succeeded=succeeded,
        failed=failed,
    )
    if all_results:
        _print_batch_report(final_report)
    else:
        console.print("[green]Nothing to insert.[/green]")


def cmd_bulk_update(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Bulk update options in an OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name")
    entity = getattr(args, "entity", None)
    attribute = getattr(args, "attribute", None)
    lang = getattr(args, "language_code", 1033)

    if not args.from_file:
        console.print("[red]--from-csv / --from-json is required for bulk update[/red]")
        return

    options = load_options(args.from_file)
    console.print(f"Loaded [bold]{len(options)}[/bold] options from {args.from_file}")

    BATCH_SIZE = 50
    total = len(options)
    all_results = []
    failed = 0
    succeeded = 0
    from OptionSetHelper import BatchReport
    try:
        from tqdm import tqdm
    except ImportError:
        console.print("[yellow]tqdm not installed. Please install tqdm for progress bars.[/yellow]")
        tqdm = None

    batch_indices = list(range(0, total, BATCH_SIZE))
    use_tqdm = tqdm is not None
    if use_tqdm:
        pbar = tqdm(total=len(batch_indices), desc="Bulk updating", unit="batch")

    def _cb(msg: str) -> None:
        pass  # tqdm progress handled after each batch

    import datetime
    for idx, i in enumerate(batch_indices):
        batch = options[i:i+BATCH_SIZE]
        start_dt = datetime.datetime.now()
        ts = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"[dim]Batch starting at {ts}[/dim]")
        # Refresh token at each batch
        try:
            svc.get_bearer_token()
        except Exception as exc:
            console.print(f"[bold red]Token refresh failed: {exc}[/bold red]")
            break
        report = svc.bulk_update_options(
            batch,
            name,
            lang,
            merge_labels=getattr(args, "merge_labels", False),
            entity_logical_name=entity,
            attribute_logical_name=attribute,
            continue_on_error=args.continue_on_error,
            progress_callback=_cb,
        )
        end_dt = datetime.datetime.now()
        duration = (end_dt - start_dt).total_seconds()
        console.print(f"[dim]Batch finished at {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (duration: {duration:.2f} seconds)[/dim]")
        all_results.extend(report.results)
        failed += report.failed
        succeeded += report.succeeded
        if use_tqdm:
            pbar.update(1)
    if use_tqdm:
        pbar.close()

    # Compose a single BatchReport for all batches
    final_report = BatchReport(
        results=all_results,
        total=total,
        succeeded=succeeded,
        failed=failed,
    )
    _print_batch_report(final_report)


def cmd_bulk_delete(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Bulk delete options from an OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name")
    entity = getattr(args, "entity", None)
    attribute = getattr(args, "attribute", None)

    if not args.from_file:
        console.print("[red]--from-csv / --from-json is required for bulk delete[/red]")
        return

    options = load_options(args.from_file)
    console.print(f"Loaded [bold]{len(options)}[/bold] options from {args.from_file}")

    if not Confirm.ask(
        f"[bold red]Delete {len(options)} options from '{name}'?[/bold red]"
    ):
        return

    BATCH_SIZE = 50
    total = len(options)
    all_results = []
    failed = 0
    succeeded = 0
    from OptionSetHelper import BatchReport
    try:
        from tqdm import tqdm
    except ImportError:
        console.print("[yellow]tqdm not installed. Please install tqdm for progress bars.[/yellow]")
        tqdm = None

    batch_indices = list(range(0, total, BATCH_SIZE))
    use_tqdm = tqdm is not None
    if use_tqdm:
        pbar = tqdm(total=len(batch_indices), desc="Bulk deleting", unit="batch")

    def _cb(msg: str) -> None:
        pass

    import datetime
    for idx, i in enumerate(batch_indices):
        batch = options[i:i+BATCH_SIZE]
        start_dt = datetime.datetime.now()
        ts = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"[dim]Batch starting at {ts}[/dim]")
        # Refresh token at each batch
        try:
            svc.get_bearer_token()
        except Exception as exc:
            console.print(f"[bold red]Token refresh failed: {exc}[/bold red]")
            break
        report = svc.bulk_delete_options(
            batch,
            name,
            entity_logical_name=entity,
            attribute_logical_name=attribute,
            continue_on_error=True,
            progress_callback=_cb,
        )
        end_dt = datetime.datetime.now()
        duration = (end_dt - start_dt).total_seconds()
        console.print(f"[dim]Batch finished at {end_dt.strftime('%Y-%m-%d %H:%M:%S')} (duration: {duration:.2f} seconds)[/dim]")
        all_results.extend(report.results)
        failed += report.failed
        succeeded += report.succeeded
        if use_tqdm:
            pbar.update(1)
    if use_tqdm:
        pbar.close()

    # Compose a single BatchReport for all batches
    final_report = BatchReport(
        results=all_results,
        total=total,
        succeeded=succeeded,
        failed=failed,
    )
    if all_results:
        _print_batch_report(final_report)
    else:
        console.print("[green]Nothing to delete.[/green]")


def cmd_insert_single(svc: DataverseOptionSetService, args: argparse.Namespace) -> None:
    """Insert a single option into an OptionSet."""
    name = args.optionset or Prompt.ask("OptionSet schema name")
    entity = getattr(args, "entity", None)
    attribute = getattr(args, "attribute", None)
    lang = getattr(args, "language_code", 1033)

    label = args.item_label or Prompt.ask("Option label")
    value = args.item_value if args.item_value is not None else IntPrompt.ask("Option value")

    option = OptionItem(label=label, value=value)

    with console.status("[bold cyan]Inserting option …"):
        resp = svc.insert_option(
            option,
            name,
            lang,
            entity_logical_name=entity,
            attribute_logical_name=attribute,
        )

    console.print(
        f"[bold green]✅ Inserted '{label}' = {value} – HTTP {resp.status_code}[/bold green]"
    )


def cmd_interactive(svc: DataverseOptionSetService) -> None:
    """Interactive menu-driven mode."""
    commands = {
        "1": ("List global OptionSets", cmd_list_global),
        "2": ("Search OptionSets by label", cmd_search),
        "3": ("Show OptionSet details", cmd_show),
        "4": ("Create global OptionSet", cmd_create_global),
        "5": ("Insert single option", cmd_insert_single),
        "6": ("Bulk insert options (from file)", cmd_bulk_insert),
        "7": ("Bulk update options (from file)", cmd_bulk_update),
        "8": ("Bulk delete options (from file)", cmd_bulk_delete),
        "q": ("Quit", None),
    }

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]Dataverse OptionSet Helper[/bold cyan]",
                subtitle="Interactive Mode",
                box=box.DOUBLE,
            )
        )
        for key, (desc, _) in commands.items():
            console.print(f"  [bold]{key}[/bold]  {desc}")
        console.print()

        choice = Prompt.ask("Select", choices=list(commands.keys()), default="q")
        if choice == "q":
            console.print("[dim]Goodbye![/dim]")
            break

        _, handler = commands[choice]
        if handler is None:
            break

        # Build a minimal namespace with common defaults
        ns = argparse.Namespace(
            optionset=None,
            label=None,
            entity=None,
            attribute=None,
            language_code=1033,
            from_file=None,
            display_label=None,
            continue_on_error=False,
            safe=True,
            merge_labels=False,
            item_label=None,
            item_value=None,
        )

        # For file-based commands, ask for file path
        if handler in (cmd_bulk_insert, cmd_bulk_update, cmd_bulk_delete):
            ns.from_file = Prompt.ask("Path to CSV/JSON file")

        # For local optionsets, optionally ask for entity/attribute
        if handler in (
            cmd_show,
            cmd_bulk_insert,
            cmd_bulk_update,
            cmd_bulk_delete,
            cmd_insert_single,
        ):
            if Confirm.ask("Is this a local (entity-scoped) OptionSet?", default=False):
                ns.entity = Prompt.ask("Entity logical name")
                ns.attribute = Prompt.ask("Attribute logical name")

        try:
            handler(svc, ns)
        except Exception as exc:
            console.print(f"[bold red]Error: {exc}[/bold red]")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dataverse OptionSet Helper CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--language-code",
        type=int,
        default=1033,
        help="Language code for labels (default: 1033 = English)",
    )

    sub = parser.add_subparsers(dest="command")

    # --- list-global ---
    sub.add_parser("list-global", help="List all global OptionSets")

    # --- search ---
    p_search = sub.add_parser("search", help="Search OptionSets by label")
    p_search.add_argument("--label", required=False, help="Search text")

    # --- show ---
    p_show = sub.add_parser("show", help="Show options of an OptionSet")
    p_show.add_argument("--optionset", "-o", required=False)
    p_show.add_argument("--entity", required=False)
    p_show.add_argument("--attribute", required=False)

    # --- create-global ---
    p_create = sub.add_parser("create-global", help="Create a global OptionSet")
    p_create.add_argument("--optionset", "-o", required=False)
    p_create.add_argument("--display-label", required=False)
    p_create.add_argument("--from-file", required=False, help="CSV or JSON file")

    # --- insert ---
    p_ins = sub.add_parser("insert", help="Insert a single option")
    p_ins.add_argument("--optionset", "-o", required=False)
    p_ins.add_argument("--entity", required=False)
    p_ins.add_argument("--attribute", required=False)
    p_ins.add_argument("--item-label", required=False)
    p_ins.add_argument("--item-value", type=int, required=False)

    # --- bulk-insert ---
    p_bi = sub.add_parser("bulk-insert", help="Batch insert options")
    p_bi.add_argument("--optionset", "-o", required=False)
    p_bi.add_argument("--from-file", required=True, help="CSV or JSON file")
    p_bi.add_argument("--entity", required=False)
    p_bi.add_argument("--attribute", required=False)
    p_bi.add_argument("--continue-on-error", action="store_true")
    p_bi.add_argument(
        "--no-safe",
        dest="safe",
        action="store_false",
        help="Skip duplicate detection",
    )

    # --- bulk-update ---
    p_bu = sub.add_parser("bulk-update", help="Batch update options")
    p_bu.add_argument("--optionset", "-o", required=False)
    p_bu.add_argument("--from-file", required=True, help="CSV or JSON file")
    p_bu.add_argument("--entity", required=False)
    p_bu.add_argument("--attribute", required=False)
    p_bu.add_argument("--merge-labels", action="store_true")
    p_bu.add_argument("--continue-on-error", action="store_true")

    # --- bulk-delete ---
    p_bd = sub.add_parser("bulk-delete", help="Batch delete options")
    p_bd.add_argument("--optionset", "-o", required=False)
    p_bd.add_argument("--from-file", required=True, help="CSV or JSON file")
    p_bd.add_argument("--entity", required=False)
    p_bd.add_argument("--attribute", required=False)
    p_bd.add_argument("--continue-on-error", action="store_true")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    console.print(
        Panel(
            "[bold cyan]Dataverse OptionSet Helper[/bold cyan]\n"
            "[dim]Manage global & local choices in your Dataverse environment[/dim]",
            box=box.DOUBLE,
        )
    )

    # Initialise service
    env_path = args.env
    try:
        with console.status("[bold cyan]Authenticating …"):
            svc = create_service_from_env(env_path)
            svc.get_bearer_token()
        console.print("[green]✅ Authenticated successfully[/green]\n")
    except Exception as exc:
        console.print(f"[bold red]Authentication failed: {exc}[/bold red]")
        sys.exit(1)

    # Dispatch
    cmd_map = {
        "list-global": cmd_list_global,
        "search": cmd_search,
        "show": cmd_show,
        "create-global": cmd_create_global,
        "insert": cmd_insert_single,
        "bulk-insert": cmd_bulk_insert,
        "bulk-update": cmd_bulk_update,
        "bulk-delete": cmd_bulk_delete,
    }

    if args.command and args.command in cmd_map:
        try:
            cmd_map[args.command](svc, args)
        except Exception as exc:
            console.print(f"[bold red]Error: {exc}[/bold red]")
            sys.exit(1)
    else:
        cmd_interactive(svc)


if __name__ == "__main__":
    main()
