export interface ToolArg {
    name: string;
    type: string;
    default: any;
    required: boolean;
    constraints: {
        min?: number;
        max?: number;
    };
    description?: string;
}

export interface Tool {
    id: string;
    name: string;
    group: string;
    description: string;
    args: ToolArg[];
}

export interface TestResult {
    status: 'passed' | 'failed' | 'no_tests';
    passed: number;
    failed: number;
    files: string[];
}

export async function fetchTools(): Promise<Tool[]> {
    const res = await fetch('/api/tools');
    return res.json();
}

export async function runTest(toolId: string): Promise<TestResult> {
    const res = await fetch(`/api/test/${toolId}`);
    return res.json();
}

export async function runTool(toolId: string, formData: FormData) {
    const res = await fetch(`/api/run/${toolId}`, {
        method: 'POST',
        body: formData
    });

    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('image')) {
        const blob = await res.blob();
        return { type: 'image', data: URL.createObjectURL(blob) };
    } else {
        return res.json();
    }
}
