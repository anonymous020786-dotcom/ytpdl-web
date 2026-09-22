"""Entry point for the ``ytpdl-web-api`` Lambda function.

Wraps the same FastAPI app (``main.py``) used by the docker-compose
deployment with Mangum's ASGI adapter — every route, auth check and Pydantic
model is unchanged; only the transport differs (Lambda Function URL instead
of uvicorn).
"""

from mangum import Mangum

from .main import app

handler = Mangum(app, lifespan="auto")
