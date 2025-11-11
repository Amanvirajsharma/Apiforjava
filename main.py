from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import tempfile
import shutil
import os
import re
from pathlib import Path
from typing import Optional, List, Tuple

app = FastAPI(title="Java Code Runner API")

# CORS (production me apne domain set karo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str
    input_data: str = ""  # optional user input

@app.get("/")
def home():
    return {"message": "Java Runner API is live 🚀"}

def extract_public_type(code: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (kind, name) where kind in {class, enum, record, interface} if public type exists.
    """
    m = re.search(r'public\s+(?:\w+\s+)*(class|enum|record|interface)\s+([A-Za-z_]\w*)', code)
    if m:
        return m.group(1), m.group(2)
    return None, None

def extract_package_name(code: str) -> Optional[str]:
    m = re.search(r'^\s*package\s+([\w\.]+)\s*;', code, re.MULTILINE)
    return m.group(1) if m else None

def code_mentions_main(code: str) -> bool:
    return re.search(
        r'public\s+static\s+void\s+main\s*\(\s*String(?:\s*\[\s*\]|\s*\.\.\.)\s*\w*\s*\)',
        code
    ) is not None

def find_main_classes_with_javap(work_dir: str, javap_path: str) -> List[str]:
    main_classes: List[str] = []
    for class_file in Path(work_dir).rglob("*.class"):
        if "$" in class_file.name:
            continue
        binary_name = str(class_file.relative_to(work_dir)).replace(os.sep, ".")[:-6]
        try:
            p = subprocess.run(
                [javap_path, "-public", "-classpath", ".", binary_name],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=work_dir
            )
            if p.returncode == 0 and (
                "public static void main(java.lang.String[])" in p.stdout
                or "public static void main(java.lang.String...)" in p.stdout
            ):
                main_classes.append(binary_name)
        except Exception:
            pass
    return main_classes

@app.post("/run-java")
def run_java_code(request: CodeRequest):
    # Locate tools
    javac_path = shutil.which("javac")
    java_path = shutil.which("java")
    javap_path = shutil.which("javap")

    if not javac_path or not java_path:
        raise HTTPException(
            status_code=500,
            detail="Java JDK not found. Ensure JDK is installed and in PATH."
        )

    work_dir = tempfile.mkdtemp(prefix="java_run_")

    try:
        # File name must match any public top-level type (class/enum/record/interface)
        public_kind, public_name = extract_public_type(request.code)
        filename = f"{public_name or 'Main'}.java"
        filepath = os.path.join(work_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.code)

        # Compile
        compile_cmd = [javac_path, "-encoding", "UTF-8", "-g:none", "-d", ".", filename]
        compile_process = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=20, cwd=work_dir
        )

        if compile_process.returncode != 0:
            return {
                "ok": False,
                "stage": "compile",
                "stdout": compile_process.stdout,
                "stderr": compile_process.stderr,
                "output": compile_process.stderr,
                "exit_code": compile_process.returncode,
            }

        # Always try to detect main via javap first (most reliable)
        candidate: Optional[str] = None
        mains: List[str] = []
        if javap_path:
            mains = find_main_classes_with_javap(work_dir, javap_path)

        if mains:
            candidate = mains[0]
        else:
            # Fallbacks if javap missing or didn't find anything
            package_name = extract_package_name(request.code)
            if public_name and code_mentions_main(request.code):
                candidate = f"{package_name}.{public_name}" if package_name else public_name
            elif public_name:
                # Try public type anyway (may fail if no main)
                candidate = f"{package_name}.{public_name}" if package_name else public_name

        if not candidate:
            raise HTTPException(status_code=400, detail="No main(String[]) method found to run.")

        # Run
        run_cmd = [java_path, "-Xmx256m", "-cp", ".", candidate]
        run_process = subprocess.run(
            run_cmd,
            input=request.input_data or "",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=work_dir
        )

        return {
            "ok": True,
            "stage": "run",
            "stdout": run_process.stdout,
            "stderr": run_process.stderr,
            "output": run_process.stdout if run_process.stdout else run_process.stderr,
            "exit_code": run_process.returncode,
            "main_class": candidate,
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=400, detail="Code execution timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

@app.get("/java-env")
def java_env():
    javac_path = shutil.which("javac")
    java_path = shutil.which("java")
    out = {}
    for name, path in [("javac", javac_path), ("java", java_path)]:
        if path:
            try:
                p = subprocess.run([path, "-version"], capture_output=True, text=True)
                out[name] = p.stdout.strip() or p.stderr.strip()
            except Exception as e:
                out[name] = f"Error: {e}"
        else:
            out[name] = "NOT FOUND"
    return out