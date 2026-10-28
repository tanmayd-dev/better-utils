import React, { useState } from 'react';
import type { Tool, ToolArg, ToolArgItems, RunPayload } from '../api';

interface DynamicFormProps {
    tool: Tool;
    onSubmit: (payload: RunPayload) => void;
    isRunning: boolean;
}

const fieldClasses = 'w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 transition-colors';

type ParseResult = { ok: true; value: unknown } | { ok: false; message: string };

export function DynamicForm({ tool, onSubmit, isRunning }: DynamicFormProps) {
    const [errors, setErrors] = useState<Record<string, string>>({});

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        const buildErrors: Record<string, string> = {};
        const hasFileArgs = tool.args.some(arg => arg.type === 'file');

        // Tools with at least one file arg go out as multipart/form-data,
        // everything else as application/json.
        let payload: RunPayload;
        if (hasFileArgs) {
            payload = { form: buildMultipart(tool.args, data, buildErrors) };
        } else {
            payload = { json: buildJsonBody(tool.args, data, buildErrors) };
        }

        if (Object.keys(buildErrors).length > 0) {
            setErrors(buildErrors);
            return; // Block submit until inline validation errors are fixed.
        }

        setErrors({});
        onSubmit(payload);
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {tool.args.map(arg => (
                <div key={arg.name} className="form-group">
                    {arg.type === 'boolean' ? (
                        <label className="flex items-center gap-3 text-sm font-medium text-slate-400 cursor-pointer">
                            <InputWidget arg={arg} />
                            <span>
                                {arg.name}
                                {arg.description && <span className="ml-2 text-xs text-slate-500">({arg.description})</span>}
                            </span>
                        </label>
                    ) : (
                        <>
                            <label className="block text-sm font-medium text-slate-400 mb-2">
                                {arg.name}
                                {jsonHint(arg)}
                                {arg.description && <span className="ml-2 text-xs text-slate-500">({arg.description})</span>}
                            </label>
                            <InputWidget arg={arg} />
                        </>
                    )}
                    {errors[arg.name] && <p className="mt-2 text-xs text-red-400">{errors[arg.name]}</p>}
                </div>
            ))}
            <button
                type="submit"
                disabled={isRunning}
                className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
                {isRunning ? 'Running...' : 'Run Tool'}
            </button>
        </form>
    );
}

function jsonHint(arg: ToolArg) {
    if (arg.type === 'list') return <span className="ml-2 text-xs text-slate-500">(JSON array)</span>;
    if (arg.type === 'dict') return <span className="ml-2 text-xs text-slate-500">(JSON object)</span>;
    return null;
}

// ---------- Payload builders ----------

function buildJsonBody(args: ToolArg[], data: FormData, errors: Record<string, string>): Record<string, unknown> {
    const body: Record<string, unknown> = {};
    for (const arg of args) {
        const raw = data.get(arg.name);
        if (typeof raw !== 'string') continue; // File args force the multipart path.
        const value = coerceArgValue(arg, raw, errors);
        if (value !== undefined) body[arg.name] = value;
    }
    return body;
}

function coerceArgValue(arg: ToolArg, raw: string, errors: Record<string, string>): unknown {
    switch (arg.type) {
        case 'boolean':
            // Unchecked checkboxes are absent from FormData, so they read as false.
            return raw === 'on';
        case 'integer':
        case 'number': {
            if (raw === '') return undefined;
            const num = Number(raw);
            if (!Number.isFinite(num)) {
                errors[arg.name] = `"${raw}" is not a valid ${arg.type}`;
                return undefined;
            }
            return num;
        }
        case 'enum': {
            if (raw === '') return undefined;
            // Restore the original (string or number) choice value.
            const choice = arg.choices?.find(c => String(c) === raw);
            return choice ?? raw;
        }
        case 'list':
        case 'dict': {
            const parsed = parseJsonArg(arg, raw);
            if (!parsed.ok) {
                errors[arg.name] = parsed.message;
                return undefined;
            }
            return parsed.value;
        }
        case 'file':
            return undefined;
        default:
            return raw === '' ? undefined : raw;
    }
}

function parseJsonArg(arg: ToolArg, raw: string): ParseResult {
    if (raw.trim() === '') return { ok: true, value: undefined };

    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        return {
            ok: false,
            message: arg.type === 'list'
                ? 'Invalid JSON — must be a JSON array, e.g. [1, 2]'
                : 'Invalid JSON — must be a JSON object, e.g. {"key": "value"}',
        };
    }

    if (arg.type === 'list' && !Array.isArray(parsed)) {
        return { ok: false, message: 'Expected a JSON array' };
    }
    if (arg.type === 'dict' && (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))) {
        return { ok: false, message: 'Expected a JSON object' };
    }

    if (arg.type === 'list' && Array.isArray(parsed) && arg.items) {
        const items = arg.items;
        const coerced: unknown[] = [];
        for (let i = 0; i < parsed.length; i++) {
            const result = coerceListElement(parsed[i], items, arg.name, i);
            if (!result.ok) return result;
            coerced.push(result.value);
        }
        return { ok: true, value: coerced };
    }

    return { ok: true, value: parsed };
}

/** Convert string elements to the declared item type ("1" -> 1, "true" -> true) where possible. */
function coerceListElement(element: unknown, items: ToolArgItems, argName: string, index: number): ParseResult {
    const wantsNumber = items.type === 'integer' || items.type === 'number';
    if (typeof element === 'string' && element.trim() !== '' && (wantsNumber || items.type === 'boolean')) {
        if (wantsNumber) {
            const num = Number(element);
            if (!Number.isFinite(num) || (items.type === 'integer' && !Number.isInteger(num))) {
                return { ok: false, message: `${argName}[${index}]: "${element}" is not a valid ${items.type}` };
            }
            return { ok: true, value: num };
        }
        if (element === 'true') return { ok: true, value: true };
        if (element === 'false') return { ok: true, value: false };
        return { ok: false, message: `${argName}[${index}]: "${element}" is not a valid boolean` };
    }
    return { ok: true, value: element };
}

function buildMultipart(args: ToolArg[], data: FormData, errors: Record<string, string>): FormData {
    const form = new FormData();
    for (const arg of args) {
        const raw = data.get(arg.name);

        if (arg.type === 'file') {
            if (raw instanceof File && raw.name !== '') {
                form.append(arg.name, raw, raw.name);
            } else if (arg.required) {
                errors[arg.name] = 'File is required';
            }
            continue;
        }

        // Booleans are always sent as "true"/"false" strings.
        if (arg.type === 'boolean') {
            form.append(arg.name, raw !== null ? 'true' : 'false');
            continue;
        }

        if (typeof raw !== 'string' || raw === '') continue; // Skip empty optional fields.

        if (arg.type === 'list' || arg.type === 'dict') {
            const parsed = parseJsonArg(arg, raw);
            if (!parsed.ok) {
                errors[arg.name] = parsed.message;
                continue;
            }
            // The textarea content is already the JSON-serialized value; send it verbatim.
            form.append(arg.name, raw);
            continue;
        }

        form.append(arg.name, raw);
    }
    return form;
}

// ---------- Inputs ----------

function InputWidget({ arg }: { arg: ToolArg }) {
    const [val, setVal] = useState<string | number>(
        typeof arg.default === 'string' || typeof arg.default === 'number' ? arg.default : (arg.min ?? '')
    );

    // Integer with both bounds: range slider (unchanged variant).
    if (arg.type === 'integer' && arg.min !== undefined && arg.max !== undefined) {
        return (
            <div className="flex items-center gap-4">
                <input
                    type="range"
                    name={arg.name}
                    min={arg.min}
                    max={arg.max}
                    value={val}
                    onChange={e => setVal(e.target.value)}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer"
                />
                <span className="text-slate-300 w-12 text-right font-mono">{val}</span>
            </div>
        );
    }

    if (arg.type === 'file') {
        return (
            <input
                type="file"
                name={arg.name}
                accept={arg.accept}
                className="block w-full text-sm text-slate-400
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-slate-800 file:text-blue-400
                    hover:file:bg-slate-700"
            />
        );
    }

    if (arg.type === 'boolean') {
        return (
            <input
                type="checkbox"
                name={arg.name}
                defaultChecked={arg.default === true}
                className="h-4 w-4 accent-blue-600 cursor-pointer"
            />
        );
    }

    if (arg.type === 'enum') {
        const hasDefault = arg.default !== null && arg.choices?.some(c => String(c) === String(arg.default));
        return (
            <select
                name={arg.name}
                defaultValue={hasDefault ? String(arg.default) : ''}
                required={arg.required}
                className={fieldClasses}
            >
                {!arg.required && <option value="">—</option>}
                {arg.choices?.map(choice => (
                    <option key={String(choice)} value={String(choice)}>{String(choice)}</option>
                ))}
            </select>
        );
    }

    if (arg.type === 'list' || arg.type === 'dict') {
        return (
            <textarea
                name={arg.name}
                rows={4}
                defaultValue={arg.default_json ?? ''}
                required={arg.required}
                className={`${fieldClasses} font-mono text-sm resize-y`}
            />
        );
    }

    // string / integer / number
    const defaultValue = typeof arg.default === 'string' || typeof arg.default === 'number' ? arg.default : '';
    return (
        <input
            type={arg.type === 'integer' || arg.type === 'number' ? 'number' : 'text'}
            name={arg.name}
            defaultValue={defaultValue}
            required={arg.required}
            min={arg.min}
            max={arg.max}
            step={arg.type === 'integer' ? 1 : arg.type === 'number' ? 'any' : undefined}
            maxLength={arg.type === 'string' ? arg.max_length : undefined}
            className={fieldClasses}
        />
    );
}
