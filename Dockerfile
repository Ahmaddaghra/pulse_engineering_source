FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.12.13
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY tests/fixtures ./tests/fixtures
ENV PATH="/app/.venv/bin:$PATH" PULSE_OBJECT_ROOT="/app/artifacts"
CMD ["uvicorn", "pulse.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
