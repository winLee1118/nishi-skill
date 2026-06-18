import { spawn } from "node:child_process";
import path from "node:path";

const appRoot = process.cwd();
export const projectRoot = path.resolve(appRoot, "..", "..");
const packagesDir = path.join(projectRoot, "packages");
const defaultDb = path.join(projectRoot, "data", "nihaixia.sqlite");
const defaultGraph = path.join(projectRoot, "knowledge", "graph");

export function pythonCommand() {
  return process.env.PYTHON || "python";
}

export function pythonEnv() {
  return {
    ...process.env,
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    PYTHONPATH: process.env.PYTHONPATH
      ? `${packagesDir}${path.delimiter}${process.env.PYTHONPATH}`
      : packagesDir,
    NIHAIXIA_DB: process.env.NIHAIXIA_DB || defaultDb,
    NIHAIXIA_GRAPH: process.env.NIHAIXIA_GRAPH || defaultGraph
  };
}

export function runPythonJson<T>(code: string, payload: unknown): Promise<T> {
  return runPython<T>(["-c", code], payload);
}

/**
 * Run a Python module (e.g. nihaixia_mcp.orchestrator) that reads a JSON payload
 * from stdin and prints a JSON result. This is the standard subprocess entry for
 * callers that are not Python and not MCP clients.
 */
export function runPythonModuleJson<T>(moduleName: string, payload: unknown): Promise<T> {
  return runPython<T>(["-m", moduleName], payload);
}

const PYTHON_TIMEOUT_MS = 60_000;

function runPython<T>(args: string[], payload: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonCommand(), ["-X", "utf8", ...args], {
      cwd: projectRoot,
      env: pythonEnv(),
      windowsHide: true
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        child.kill("SIGTERM");
        reject(new Error(`Python process timed out after ${PYTHON_TIMEOUT_MS}ms`));
      }
    }, PYTHON_TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");

    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });

    child.on("error", (err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(err);
      }
    });
    child.on("close", (exitCode) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);

      if (exitCode !== 0) {
        reject(new Error(stderr || `Python exited with code ${exitCode}`));
        return;
      }

      try {
        resolve(JSON.parse(stdout.trim()) as T);
      } catch (error) {
        reject(new Error(`Python returned invalid JSON: ${String(error)}\n${stdout}`));
      }
    });

    child.stdin.write(JSON.stringify(payload), "utf8");
    child.stdin.end();
  });
}
