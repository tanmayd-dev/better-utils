import React, { useState } from 'react';
import type { Tool, ToolArg } from '../api';

interface DynamicFormProps {
    tool: Tool;
    onSubmit: (formData: FormData) => void;
    isRunning: boolean;
}

export function DynamicForm({ tool, onSubmit, isRunning }: DynamicFormProps) {
    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);
        onSubmit(formData);
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {tool.args.map(arg => (
                <div key={arg.name} className="form-group">
                    <label className="block text-sm font-medium text-slate-400 mb-2">
                        {arg.name}
                        {arg.description && <span className="ml-2 text-xs text-slate-500">({arg.description})</span>}
                    </label>
                    <InputWidget arg={arg} />
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

function InputWidget({ arg }: { arg: ToolArg }) {
    const [val, setVal] = useState(arg.default ?? (arg.constraints.min ?? ''));

    if (arg.type === 'integer' && arg.constraints.min !== undefined && arg.constraints.max !== undefined) {
        return (
            <div className="flex items-center gap-4">
                <input
                    type="range"
                    name={arg.name}
                    min={arg.constraints.min}
                    max={arg.constraints.max}
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
                className="block w-full text-sm text-slate-400
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-slate-800 file:text-blue-400
                    hover:file:bg-slate-700"
            />
        );
    }

    return (
        <input
            type={arg.type === 'integer' || arg.type === 'number' ? 'number' : 'text'}
            name={arg.name}
            defaultValue={arg.default}
            required={arg.required}
            className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 transition-colors"
        />
    );
}
