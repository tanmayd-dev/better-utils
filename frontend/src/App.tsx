import { useEffect, useState } from 'react';
import { fetchTools, runTool, runTest } from './api';
import type { Tool, TestResult, Result, RunPayload, ModuleError } from './api';
import { DynamicForm } from './components/DynamicForm';
import { Terminal, Play, CheckCircle, XCircle, AlertCircle, ChevronRight } from 'lucide-react';
import './index.css';

function App() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [moduleErrors, setModuleErrors] = useState<ModuleError[]>([]);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [testStatus, setTestStatus] = useState<TestResult | null>(null);
  const [showTestOutput, setShowTestOutput] = useState(false);

  useEffect(() => {
    fetchTools()
      .then(catalog => {
        setTools(catalog.tools);
        setModuleErrors(catalog.errors);
      })
      .catch(err => console.error(err));
  }, []);

  const handleSelectTool = async (tool: Tool) => {
    setSelectedTool(tool);
    setResult(null);
    setTestStatus(null);
    setShowTestOutput(false);

    try {
      const status = await runTest(tool.id);
      setTestStatus(status);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSubmit = async (payload: RunPayload) => {
    if (!selectedTool) return;
    setIsRunning(true);
    try {
      setResult(await runTool(selectedTool.id, payload));
    } catch (e) {
      setResult({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setIsRunning(false);
    }
  };

  // Group tools
  const groups: Record<string, Tool[]> = {};
  tools.forEach(t => {
    if (!groups[t.group]) groups[t.group] = [];
    groups[t.group].push(t);
  });

  const isTestBroken = testStatus !== null
    && (testStatus.status === 'failed' || testStatus.status === 'error');

  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-6 border-b border-slate-800 flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Terminal size={20} className="text-white" />
          </div>
          <h1 className="font-bold text-lg tracking-tight">Better Utils</h1>
        </div>
        {moduleErrors.length > 0 && (
          <div className="mx-4 mt-4 rounded-lg border border-red-500/20 bg-red-500/10 p-3 space-y-1">
            {moduleErrors.map(error => (
              <p
                key={error.path}
                title={error.traceback ?? error.error}
                className="text-xs text-red-400 truncate"
              >
                {error.path} — {error.error}
              </p>
            ))}
          </div>
        )}
        <nav className="flex-1 overflow-y-auto p-4 space-y-6">
          {Object.entries(groups).map(([group, groupTools]) => (
            <div key={group}>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 px-2">{group}</h3>
              <div className="space-y-1">
                {groupTools.map(tool => (
                  <button
                    key={tool.id}
                    onClick={() => handleSelectTool(tool)}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm transition-all flex items-center justify-between group ${selectedTool?.id === tool.id
                      ? 'bg-blue-600/10 text-blue-400'
                      : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                  >
                    {tool.name}
                    {selectedTool?.id === tool.id && <ChevronRight size={14} />}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        {selectedTool ? (
          <div className="max-w-3xl mx-auto p-12">
            <header className="mb-10 border-b border-slate-800 pb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-3xl font-bold text-white">{selectedTool.name}</h2>
                {testStatus && (isTestBroken ? (
                  <button
                    type="button"
                    onClick={() => setShowTestOutput(value => !value)}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border bg-red-500/10 border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
                  >
                    {testStatus.status === 'failed' ? <XCircle size={14} /> : <AlertCircle size={14} />}
                    {testStatus.status === 'failed' ? 'Tests Failing' : 'Test Error'}
                  </button>
                ) : (
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${testStatus.status === 'passed'
                    ? 'bg-green-500/10 border-green-500/20 text-green-400'
                    : 'bg-slate-800 border-slate-700 text-slate-400'
                    }`}>
                    {testStatus.status === 'passed' ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                    {testStatus.status === 'passed' ? 'Tests Passing' : testStatus.status === 'no_tests' ? 'No Tests' : 'Test Error'}
                  </div>
                ))}
              </div>
              <p className="text-slate-400 text-lg leading-relaxed">{selectedTool.description}</p>
            </header>

            {testStatus && (testStatus.status === 'failed' || testStatus.status === 'error') && showTestOutput && (
              <pre className="mb-8 max-h-64 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-red-300 whitespace-pre-wrap">
                {testStatus.output}
              </pre>
            )}

            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-8 mb-8">
              <DynamicForm key={selectedTool.id} tool={selectedTool} onSubmit={handleSubmit} isRunning={isRunning} />
            </div>

            {result && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-300">
                <div className="flex items-baseline gap-3 mb-4">
                  <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider">Result</h3>
                  {result.ok && <span className="text-xs text-slate-500">{result.elapsed_ms} ms</span>}
                </div>
                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                  {result.ok && result.type === 'image' ? (
                    <div className="p-4 flex justify-center bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgZmlsbD0iIzMzMyI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIiBmaWxsPSIjMjIyIi8+PHJlY3QgeD0iMTAiIHk9IjEwIiB3aWR0aD0iMTAiIGhlaWdodD0iMTAiIGZpbGw9IiMyMjIiLz48L3N2Zz4=')]">
                      <img src={result.image_url ?? ''} alt="Result" className="max-w-full rounded shadow-lg" />
                    </div>
                  ) : !result.ok ? (
                    <div className="p-6 text-red-400 bg-red-500/5 border-l-4 border-red-500 space-y-3">
                      <p className="whitespace-pre-wrap">{result.error}</p>
                      {result.validation !== undefined && result.validation.length > 0 && (
                        <ul className="text-xs text-red-300/80 space-y-0.5">
                          {result.validation.map(issue => (
                            <li key={`${issue.name}: ${issue.msg}`}>{issue.name}: {issue.msg}</li>
                          ))}
                        </ul>
                      )}
                      {result.traceback !== undefined && (
                        <pre className="overflow-x-auto font-mono text-xs text-red-300/70">{result.traceback}</pre>
                      )}
                    </div>
                  ) : (
                    <pre className="p-6 overflow-x-auto font-mono text-sm text-blue-300">
                      {result.type === 'text' ? String(result.data) : JSON.stringify(result.data, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-500">
            <div className="w-16 h-16 bg-slate-900 rounded-2xl flex items-center justify-center mb-6 rotate-12">
              <Play size={32} className="text-slate-600" />
            </div>
            <p className="text-lg">Select a tool from the sidebar to get started</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
