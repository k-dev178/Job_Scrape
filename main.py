from fastapi import FastAPI

app = FastAPI(title="Job Scrape API", version="0.1.0")


@app.get("/")
def root():
    return {"message": "Job Scrape API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
