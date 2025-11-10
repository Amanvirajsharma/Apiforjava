from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import uuid
import shutil
import re

app = FastAPI(title="Java Code Runner API")

# Ensure Java path is included
os.environ["PATH"] += os.pathsep + r"C:\Program Files\Java\jdk-25\bin"

@app.get("/")
def home():
    return {"message": "Java Runner API is live 🚀"}


class CodeRequest(BaseModel):
    code: str
    input_data: str = ""  # optional user input


@app.post("/run-java")
def run_java_code(request: CodeRequest):
    javac_path = shutil.which("javac")
    java_path = shutil.which("java")

    if not javac_path or not java_path:
        raise HTTPException(
            status_code=500,
            detail="Java not found. Please install JDK and add it to PATH."
        )

    work_dir = os.path.abspath("temp_java")
    os.makedirs(work_dir, exist_ok=True)

    # Try to find the public class name
    match = re.search(r'public\s+class\s+(\w+)', request.code)
    classname = match.group(1) if match else "Main"

    filename = f"{classname}.java"
    filepath = os.path.join(work_dir, filename)

    try:
        # Write code to file
        with open(filepath, "w") as f:
            f.write(request.code)

        # Compile Java file
        compile_process = subprocess.run(
            [javac_path, filename],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=work_dir
        )

        if compile_process.returncode != 0:
            return {"output": compile_process.stderr}

        # Run Java class
        run_process = subprocess.run(
            [java_path, classname],
            input=request.input_data,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=work_dir
        )

        return {"output": run_process.stdout or run_process.stderr}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=400, detail="Code execution timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean temp files
        try:
            for file in os.listdir(work_dir):
                os.remove(os.path.join(work_dir, file))
        except:
            pass
