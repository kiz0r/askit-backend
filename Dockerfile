FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY ./app ./app

# Copy alembic configuration
COPY alembic.ini ./
COPY ./alembic ./alembic

# Set Python path
ENV PYTHONPATH=/app

# Run the application using uv
CMD ["uv", "run", "--no-dev", "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
