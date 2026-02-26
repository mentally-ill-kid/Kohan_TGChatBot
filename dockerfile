FROM python:3

WORKDIR /app

RUN pip install --upgrade pip

COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
