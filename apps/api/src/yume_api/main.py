from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Ame-no-Uzume")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
