# The sandbox the download recipes are tested in (test_recipes.py): Python and only what the recipes need. Each recipe
# runs in a fresh container that sees nothing of the host but its own empty work folder.
FROM python:3.12-slim
COPY requirements-recipes.txt /tmp/requirements-recipes.txt
RUN pip install --no-cache-dir -r /tmp/requirements-recipes.txt && useradd --create-home recipe
USER recipe
WORKDIR /work
