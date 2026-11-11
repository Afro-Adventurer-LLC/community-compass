"""Lambda entry: `handler` is the Mangum-wrapped FastAPI app.

Configure API Gateway to proxy to this handler (see docs/AWS_DEPLOY.md).
"""
from .main import handler
