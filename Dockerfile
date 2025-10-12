FROM python:3.11-slim

WORKDIR /app

# Instalar dependências de sistema necessárias
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Expor porta
EXPOSE 3001

# Comando para rodar
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]