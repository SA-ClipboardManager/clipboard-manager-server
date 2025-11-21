from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "waiting_for_development"}

@app.get("/health")
def health_check():
    return {"status": "ok"}