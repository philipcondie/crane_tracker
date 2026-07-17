from fastapi import FastAPI

from app.routes.crane import crane_router

app = FastAPI()

app.include_router(crane_router)
