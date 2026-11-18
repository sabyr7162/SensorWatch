from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy import *

import logging
import sys
import time

from database import initialize_database
from routers import router 
from alert import lifespan
from security import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding='utf-8')
    ]
)

logger = logging.getLogger("Iot_backend")

app = FastAPI(title='HomeSensor app', lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
app.state.limiter = limiter
initialize_database()


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={'detail': "Too many attempts. Try again later"},
        headers={"Retry-After": "60"}
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"METHOD: {request.method} PATH: {request.url.path} "
        f"STATUS: {response.status_code} TIME: {process_time:.2f}ms"
    )
    return response

