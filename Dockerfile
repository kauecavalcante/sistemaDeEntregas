FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Comando para executar a aplicação quando o contêiner iniciar
# Render espera que a aplicação rode na porta 10000 e escute em 0.0.0.0
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]