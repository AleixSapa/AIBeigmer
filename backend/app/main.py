from fastapi import FastAPI

app = FastAPI(title="AIBeigmer API", version="0.1.0", description="Real AI model benchmarking platform")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AIBeigmer"}
