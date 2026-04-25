"""Fast CLI client for PMS API server."""

import asyncio

import click
from rich.console import Console

from pms.client.http_client import PMSClient
from pms.runtime.defaults import LOCAL_SERVER_DEFAULT_BASE_URL

console = Console()


@click.group()
@click.option("--server", default=LOCAL_SERVER_DEFAULT_BASE_URL, help="PMS server URL")
@click.pass_context
def cli(ctx: click.Context, server: str) -> None:
    """PMS Client - Fast compiled client for PMS API server."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


@cli.group()
def task() -> None:
    """Task operations."""
    pass


@task.command("create")
@click.argument("project_id")
@click.argument("title")
@click.option("-c", "--complexity", type=int, help="Complexity points (1-100)")
@click.option("-p", "--priority", default="medium", help="Priority")
@click.pass_context
def task_create(
    ctx: click.Context,
    project_id: str,
    title: str,
    complexity: int | None,
    priority: str,
) -> None:
    """Create a task."""

    async def run() -> None:
        async with PMSClient(base_url=ctx.obj["server"]) as client:
            task = await client.create_task(
                project_id=project_id,
                title=title,
                complexity_points=complexity,
                priority=priority,
            )
            console.print(f"[green]Created task:[/green] {task['title']}")
            console.print(f"[dim]ID: {task['id']}[/dim]")
            console.print(f"[dim]Complexity: {task['complexity_points']} points[/dim]")

    asyncio.run(run())


@task.command("checkout")
@click.argument("task_id")
@click.option("--agent-id", required=True, help="Agent session ID")
@click.option("--lease", default=300, help="Lease seconds")
@click.pass_context
def task_checkout(ctx: click.Context, task_id: str, agent_id: str, lease: int) -> None:
    """Checkout a task."""

    async def run() -> None:
        async with PMSClient(base_url=ctx.obj["server"]) as client:
            result = await client.checkout_task(task_id, agent_id, lease)
            console.print(f"[green]Checked out task {task_id}[/green]")
            console.print(f"[dim]Until: {result['checkout_lease_until']}[/dim]")

    asyncio.run(run())


@task.command("progress")
@click.argument("task_id")
@click.argument("percent", type=int)
@click.argument("message")
@click.option("--by", "updated_by", required=True, help="Updated by")
@click.pass_context
def task_progress(
    ctx: click.Context, task_id: str, percent: int, message: str, updated_by: str
) -> None:
    """Update task progress."""

    async def run() -> None:
        async with PMSClient(base_url=ctx.obj["server"]) as client:
            await client.update_progress(task_id, percent, message, updated_by)
            console.print(f"[green]Updated progress: {percent}%[/green]")

    asyncio.run(run())


@cli.group()
def product() -> None:
    """Product operations."""
    pass


@product.command("create")
@click.argument("name")
@click.option("-d", "--description", help="Description")
@click.option("-v", "--vision", help="Vision")
@click.pass_context
def product_create(
    ctx: click.Context, name: str, description: str | None, vision: str | None
) -> None:
    """Create a product."""

    async def run() -> None:
        async with PMSClient(base_url=ctx.obj["server"]) as client:
            product = await client.create_product(name, description, vision)
            console.print(f"[green]Created product:[/green] {product['name']}")
            console.print(f"[dim]ID: {product['id']}[/dim]")

    asyncio.run(run())


@product.command("list")
@click.pass_context
def product_list(ctx: click.Context) -> None:
    """List products."""

    async def run() -> None:
        async with PMSClient(base_url=ctx.obj["server"]) as client:
            result = await client.list_products()
            console.print(f"[bold]Products ({result.get('total_count', 0)}):[/bold]")
            for p in result.get("items", []):
                console.print(f"  • {p['name']} ({p['status']}) - {p['id']}")

    asyncio.run(run())


if __name__ == "__main__":
    cli()
