"""Entry point for `python -m minicode`."""

from .cli import main

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
