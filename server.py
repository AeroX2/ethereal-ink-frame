from typing import Union
from fastapi import FastAPI, BackgroundTasks

import uuid
import tasks

app = FastAPI()


@app.get("/")
def root():
    return {"Hello": "World"}


@app.get("/generate")
def generate(prompt: str):
    tasks.generate_image(prompt, "generated/{}.png".format(uuid.uuid4()))
    return {"status": "ok"}
    
@app.get("/cancel")
def cancel(prompt: str):
    tasks.cancel_generate_image()
    return {"status": "ok"}