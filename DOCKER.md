# 🐳 Dockerization Guide for Diabetes Dost

This guide explains how to run **Diabetes Dost** (AI Voice Pre-Screener for Diabetes) inside Docker containers.

---

## ⚡ Quickstart with Docker Compose (Recommended)

### 1. Configure Environment (Optional)
Ensure your `.env` file exists in `Project_1-main/.env` or the project root with your API key:
```env
SARVAM_API_KEY=your_sarvam_api_key_here
PORT=8000
HOST=0.0.0.0
```

### 2. Build and Start the Application
Run the following command from the repository root:
```bash
docker compose up --build
```
Or to run in detached (background) mode:
```bash
docker compose up -d --build
```

### 3. Open the App in Your Browser
- **Patient Voice Consultation App:** [http://localhost:8000](http://localhost:8000)
- **Clinician / Admin Portal:** [http://localhost:8000/admin](http://localhost:8000/admin)
- **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Stop the Container
```bash
docker compose down
```

---

## 🛠️ Running with Standard Docker CLI

### 1. Build the Docker Image
```bash
docker build -t diabetes-dost:latest .
```

### 2. Run the Docker Container
```bash
docker run -d \
  --name diabetes_dost_app \
  -p 8000:8000 \
  -e SARVAM_API_KEY=your_sarvam_api_key_here \
  -v "$(pwd)/Project_1-main/outputs/database:/app/Project_1-main/outputs/database" \
  -v "$(pwd)/Project_1-main/outputs/reports:/app/Project_1-main/outputs/reports" \
  -v "$(pwd)/Project_1-main/datasets:/app/Project_1-main/datasets" \
  diabetes-dost:latest
```

*(On Windows PowerShell, replace `$(pwd)` with `${PWD}`)*

---

## 📁 Persistent Data & Volumes

The Docker configuration automatically maps and persists the following host directories:
- **`outputs/database/`**: Persistent SQLite database storing all consultations, emergency triage alerts, and patient records.
- **`outputs/reports/`**: Stored PDF / JSON clinical triage summary reports.
- **`outputs/logs/`**: Pipeline and error audit logs.
- **`datasets/`**: Audio datasets, preprocessed WAVs, and transcription manifests.

---

## 🔍 Checking Container Health & Logs

- **View real-time logs:**
  ```bash
  docker logs -f diabetes_dost_app
  ```
- **Check health status:**
  ```bash
  docker ps
  ```
- **Access container bash/sh terminal:**
  ```bash
  docker exec -it diabetes_dost_app bash
  ```
