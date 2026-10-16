FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY build_frontend.py ./build_frontend.py
RUN python build_frontend.py
COPY reference/kato_ru.csv ./reference/kato_ru.csv
COPY reference ./reference
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
