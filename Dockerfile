# Pins the Python version so the pipeline runs identically on any machine.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so this layer is cached unless requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the batch pipeline on the sample input. No key needed — the
# pipeline auto-selects the heuristic mock unless GEMINI_API_KEY is set. Prints
# the review summary; writes artifacts under /app/outputs.
CMD ["python", "main.py", "--input", "quotes.json"]
