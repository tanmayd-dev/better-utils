import { useEffect, useState } from 'react';
import { fetchTools, runTool, runTest } from './api';
import type { Tool, TestResult } from './api';
import { DynamicForm } from './components/DynamicForm';
import { Terminal, Play, CheckCircle, XCircle, AlertCircle, ChevronRight } from 'lucide-react';
import './index.css';

function App() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [result, setResult] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [testStatus, setTestStatus] = useState<TestResult | null>(null);

  useEffect(() => {
    fetchTools().then(setTools);
  }, []);

  const handleSelectTool = async (tool: Tool) => {
    setSelectedTool(tool);
    setResult(null);
    setTestStatus(null);

    try {
      const status = await runTest(tool.id);
      setTestStatus(status);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSubmit = async (formData: FormData) => {
    if (!selectedTool) return;
    setIsRunning(true);
    try {
      const res = await runTool(selectedTool.id, formData);
      setResult(res);
    } catch (e) {
      setResult({ error: String(e) });
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
                {testStatus && (
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${testStatus.status === 'passed'
                    ? 'bg-green-500/10 border-green-500/20 text-green-400'
                    : testStatus.status === 'failed'
                      ? 'bg-red-500/10 border-red-500/20 text-red-400'
                      : 'bg-slate-800 border-slate-700 text-slate-400'
                    }`}>
                    {testStatus.status === 'passed' && <CheckCircle size={14} />}
                    {testStatus.status === 'failed' && <XCircle size={14} />}
                    {testStatus.status === 'no_tests' && <AlertCircle size={14} />}
                    {testStatus.status === 'passed' ? 'Tests Passing' : testStatus.status === 'failed' ? 'Tests Failing' : 'No Tests'}
                  </div>
                )}
              </div>
              <p className="text-slate-400 text-lg leading-relaxed">{selectedTool.description}</p>
            </header>

            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-8 mb-8">
              <DynamicForm tool={selectedTool} onSubmit={handleSubmit} isRunning={isRunning} />
            </div>

            {result && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-300">
                <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">Result</h3>
                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                  {result.type === 'image' ? (
                    <div className="p-4 flex justify-center bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgZmlsbD0iIzMzMyI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIiBmaWxsPSIjMjIyIi8+PHJlY3QgeD0iMTAiIHk9IjEwIiB3aWR0aD0iMTAiIGhlaWdodD0iMTAiIGZpbGw9IiMyMjIiLz48L3N2Zz4=')]">
                      <img src={result.data} alt="Result" className="max-w-full rounded shadow-lg" />
                    </div>
                  ) : result.error ? (
                    <div className="p-6 text-red-400 bg-red-500/5 border-l-4 border-red-500">
                      {result.error}
                    </div>
                  ) : (
                    <pre className="p-6 overflow-x-auto font-mono text-sm text-blue-300">
                      {result.type === 'text' ? result.data : JSON.stringify(result, null, 2)}
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
