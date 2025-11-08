from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import uuid
import shutil

app = FastAPI(title="Java Code Runner API")

class CodeRequest(BaseModel):
    code: str
    input_data: str = ""  # optional user input

@app.post("/run-java")
def run_java_code(request: CodeRequest):
    # check if java is installed
    javac_path = shutil.which("javac")
    java_path = shutil.which("java")

    if not javac_path or not java_path:
        raise HTTPException(
            status_code=500,
            detail="Java not found. Please install JDK and add it to PATH."
        )

    # create a temp file
    filename = f"Temp_{uuid.uuid4().hex}.java"
    try:
        with open(filename, "w") as f:
            f.write(request.code)

        # compile Java code
        compile_process = subprocess.run(
            [javac_path, filename],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_process.returncode != 0:
            return {"output": compile_process.stderr}

        # get class name (Main class)
        classname = os.path.splitext(os.path.basename(filename))[0]

        # run compiled java program
        run_process = subprocess.run(
            [java_path, classname],
            input=request.input_data,
            capture_output=True,
            text=True,
            timeout=10
        )

        return {"output": run_process.stdout or run_process.stderr}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=400, detail="Code execution timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # clean up temp files
        try:
            if os.path.exists(filename):
                os.remove(filename)
            class_file = filename.replace(".java", ".class")
            if os.path.exists(class_file):
                os.remove(class_file)
        except:
            pass
