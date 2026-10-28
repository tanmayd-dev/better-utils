// API contract types and fetch helpers for the Better Utils dashboard.

// ---------- Catalog ----------

export type ToolArgType =
    | 'string'
    | 'integer'
    | 'number'
    | 'boolean'
    | 'enum'
    | 'list'
    | 'dict'
    | 'file';

export interface ToolArgItems {
    type: 'string' | 'integer' | 'number' | 'boolean';
}

export interface ToolArg {
    name: string;
    type: ToolArgType;
    required: boolean;
    default: string | number | boolean | null;
    /** For list/dict args: default serialized as JSON string, used to seed the textarea. */
    default_json?: string;
    description?: string;
    nullable?: boolean;
    /** For enum args. */
    choices?: (string | number)[];
    /** Numeric bounds (integer/number args). */
    min?: number;
    max?: number;
    /** String length bounds (string args). */
    min_length?: number;
    max_length?: number;
    /** File accept attribute, e.g. "image/*". */
    accept?: string;
    /** For list args: element type. */
    items?: ToolArgItems;
}

export interface Tool {
    id: string;
    name: string;
    group: string;
    description: string;
    long_description?: string;
    args: ToolArg[];
}

export interface ModuleError {
    path: string;
    error: string;
    traceback?: string;
}

export interface ToolsCatalog {
    tools: Tool[];
    errors: ModuleError[];
}

export async function fetchTools(): Promise<ToolsCatalog> {
    const res = await fetch('/api/tools');
    if (!res.ok) {
        throw new Error(`Failed to load tools (${res.status}${res.statusText ? ` ${res.statusText}` : ''})`);
    }
    return (await res.json()) as ToolsCatalog;
}

// ---------- Tests ----------

export interface TestResult {
    status: 'passed' | 'failed' | 'no_tests' | 'error';
    passed: number;
    failed: number;
    output: string;
    duration_ms: number;
}

export async function runTest(toolId: string): Promise<TestResult> {
    const res = await fetch(`/api/test/${toolId}`, { method: 'POST' });
    if (!res.ok) {
        throw new Error(`Test runner failed (${res.status}${res.statusText ? ` ${res.statusText}` : ''})`);
    }
    return (await res.json()) as TestResult;
}

// ---------- Run ----------

/**
 * Either a JSON body (tools without file args) or a FormData body
 * (tools with at least one file arg). `form` takes precedence.
 */
export interface RunPayload {
    json?: Record<string, unknown>;
    form?: FormData;
}

export interface RunSuccess {
    ok: true;
    type: 'json' | 'text' | 'image';
    data: unknown;
    image_url: string | null;
    elapsed_ms: number;
}

export interface ValidationIssue {
    name: string;
    msg: string;
}

export interface RunError {
    ok: false;
    error: string;
    traceback?: string;
    validation?: ValidationIssue[];
}

export type Result = RunSuccess | RunError;

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null;
}

function statusMessage(status: number, statusText: string): string {
    return statusText ? `${status} ${statusText}` : `Request failed (${status})`;
}

/** Normalize a non-200 body: `{"ok":false,"error":...}`, `{"detail":...}`, or falls back to status text. */
function errorFrom(body: unknown, status: number, statusText: string): RunError {
    if (isRecord(body)) {
        const message =
            typeof body.error === 'string' ? body.error
            : typeof body.detail === 'string' ? body.detail
            : null;
        if (message !== null) {
            const result: RunError = { ok: false, error: message };
            if (typeof body.traceback === 'string') result.traceback = body.traceback;
            if (Array.isArray(body.validation)) {
                const validation = body.validation
                    .filter(isRecord)
                    .map(issue => ({ name: String(issue.name), msg: String(issue.msg) }));
                if (validation.length > 0) result.validation = validation;
            }
            return result;
        }
    }
    return { ok: false, error: statusMessage(status, statusText) };
}

function isSuccessBody(body: unknown): body is RunSuccess {
    return isRecord(body)
        && body.ok === true
        && (body.type === 'json' || body.type === 'text' || body.type === 'image');
}

export async function runTool(toolId: string, payload: RunPayload): Promise<Result> {
    const init: RequestInit = { method: 'POST' };
    if (payload.form) {
        init.body = payload.form;
    } else {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(payload.json ?? {});
    }

    const res = await fetch(`/api/run/${toolId}`, init);

    let body: unknown = null;
    try {
        body = await res.json();
    } catch {
        // Non-JSON body: fall back to the status text below.
    }

    if (!res.ok) return errorFrom(body, res.status, res.statusText);
    if (isSuccessBody(body)) return body;
    return { ok: false, error: 'Unexpected response from server' };
}
