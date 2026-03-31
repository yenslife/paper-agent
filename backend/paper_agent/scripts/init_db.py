import asyncio

import asyncpg
from rich.console import Console
from sqlalchemy.engine import make_url

from paper_agent.config import get_settings
from paper_agent.db import initialize_database

console = Console()


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def create_database_if_missing(database_url: str) -> bool:
    url = make_url(database_url)
    database_name = url.database
    if not database_name:
        raise ValueError("DATABASE_URL 缺少 database 名稱。")

    admin_database = "postgres" if database_name != "postgres" else "template1"
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port or 5432,
        database=admin_database,
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            database_name,
        )
        if exists:
            return False

        await connection.execute(f"CREATE DATABASE {quote_identifier(database_name)}")
        return True
    finally:
        await connection.close()


async def main() -> None:
    settings = get_settings()
    console.print("[bold cyan]Initializing Paper Agent database...[/bold cyan]")
    console.print(f"Target database: [bold]{make_url(settings.database_url).database}[/bold]")

    created = await create_database_if_missing(settings.database_url)
    if created:
        console.print("[green]Database created.[/green]")
    else:
        console.print("[yellow]Database already exists.[/yellow]")

    await initialize_database()
    console.print("[green]pgvector extension and tables are ready.[/green]")


if __name__ == "__main__":
    asyncio.run(main())
