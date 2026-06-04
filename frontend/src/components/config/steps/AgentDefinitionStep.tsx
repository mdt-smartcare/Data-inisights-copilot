/**
 * AgentDefinitionStep — Step 5 of the agent-create wizard.
 *
 * Surfaces the AI-bootstrapped Agent Definition (role, personas, KPIs,
 * guardrails, sample Q&A) so the user can review, edit, and accept before
 * the system prompt is generated.
 *
 * Bootstrap is kicked off server-side on the data-dictionary save (Step 3).
 * This component polls the agent-definition endpoint and renders a
 * loading/empty/populated state accordingly.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  bootstrapAgentDefinition,
  pollAgentDefinition,
  type AgentDefinition,
  type SampleQuestion,
} from '../../../services/api';

interface AgentDefinitionStepProps {
  agentId: string;
  versionId: number;
  value: AgentDefinition | null;
  onChange: (value: AgentDefinition) => void;
}

const EMPTY_DEFINITION: AgentDefinition = {
  role: '',
  responsibilities: [],
  business_objectives: [],
  target_personas: [],
  analytical_capabilities: [],
  limitations: [],
  response_style: { tone: '', format: '', verbosity: '' },
  kpis_metrics: [],
  domain_rules: [],
  guardrails: [],
  sample_questions: [],
  confidence_per_field: {},
  ai_drafted_fields: [],
};

type ListField =
  | 'responsibilities'
  | 'business_objectives'
  | 'target_personas'
  | 'analytical_capabilities'
  | 'limitations'
  | 'kpis_metrics'
  | 'domain_rules'
  | 'guardrails';

const LIST_FIELDS: { key: ListField; label: string }[] = [
  { key: 'responsibilities', label: 'Responsibilities' },
  { key: 'business_objectives', label: 'Business Objectives' },
  { key: 'target_personas', label: 'Target Users / Personas' },
  { key: 'analytical_capabilities', label: 'Analytical Capabilities' },
  { key: 'limitations', label: 'Limitations' },
  { key: 'kpis_metrics', label: 'Priority KPIs / Metrics' },
  { key: 'domain_rules', label: 'Domain Rules' },
  { key: 'guardrails', label: 'Guardrails' },
];

const BOOTSTRAP_STAGES = [
  'Introspecting tables and columns',
  'Mapping foreign-key relationships',
  'Sampling categorical values (PHI-redacted)',
  'Inferring role, KPIs, and guardrails',
  'Drafting sample questions',
];

const LoadingState: React.FC = () => {
  const [elapsedSec, setElapsedSec] = useState(0);
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    // Advance through stages every ~6 seconds to give the user a sense of progress.
    if (stageIdx >= BOOTSTRAP_STAGES.length - 1) return;
    const t = window.setTimeout(() => setStageIdx((i) => i + 1), 6000);
    return () => window.clearTimeout(t);
  }, [stageIdx]);

  return (
    <div className="space-y-6">
      {/* Hero banner */}
      <div className="relative overflow-hidden rounded-xl border border-purple-200 bg-gradient-to-br from-purple-50 via-fuchsia-50 to-pink-50 p-6">
        <div className="absolute inset-0 -translate-x-full animate-[shimmer_2.4s_infinite] bg-gradient-to-r from-transparent via-white/60 to-transparent" />
        <div className="relative">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-purple-600 text-lg text-white shadow-sm">
              ✨
            </span>
            <div>
              <div className="text-base font-semibold text-purple-900">
                AI is reading your schema…
              </div>
              <div className="mt-0.5 text-sm text-purple-700">
                Populating role, KPIs, guardrails, and sample questions.
              </div>
            </div>
            <div className="ml-auto text-xs font-medium text-purple-700">
              {elapsedSec}s elapsed
            </div>
          </div>

          {/* Stage list */}
          <ul className="mt-5 space-y-2 text-sm">
            {BOOTSTRAP_STAGES.map((label, i) => {
              const done = i < stageIdx;
              const active = i === stageIdx;
              return (
                <li key={label} className="flex items-center gap-3">
                  <span
                    className={
                      done
                        ? 'inline-flex h-5 w-5 items-center justify-center rounded-full bg-purple-600 text-[10px] font-bold text-white'
                        : active
                        ? 'inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-purple-500 bg-white'
                        : 'inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-purple-200 bg-white'
                    }
                  >
                    {done ? '✓' : active ? (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-purple-500" />
                    ) : null}
                  </span>
                  <span
                    className={
                      done
                        ? 'text-purple-900'
                        : active
                        ? 'font-medium text-purple-900'
                        : 'text-purple-500'
                    }
                  >
                    {label}
                  </span>
                </li>
              );
            })}
          </ul>
          {elapsedSec > 120 && (
            <div className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Taking longer than usual. If this persists past 5 minutes, the bootstrap may have stalled —
              try the Retry button that will surface on failure, or refill the form manually.
            </div>
          )}
        </div>
      </div>

      {/* Skeleton placeholders so the page doesn't look empty */}
      <div className="space-y-5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="rounded-lg border border-gray-200 p-4">
            <div className="h-3 w-32 animate-pulse rounded bg-gray-200" />
            <div className="mt-3 space-y-2">
              <div className="h-2.5 w-full animate-pulse rounded bg-gray-100" />
              <div className="h-2.5 w-5/6 animate-pulse rounded bg-gray-100" />
              <div className="h-2.5 w-3/4 animate-pulse rounded bg-gray-100" />
            </div>
          </div>
        ))}
      </div>

      {/* Shimmer keyframes — defined inline so we don't need a tailwind config change */}
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
};

export const AgentDefinitionStep: React.FC<AgentDefinitionStepProps> = ({
  agentId,
  versionId,
  value,
  onChange,
}) => {
  const [status, setStatus] = useState<'not_started' | 'pending' | 'completed' | 'failed'>(
    value ? 'completed' : 'not_started',
  );
  const [error, setError] = useState<string | null>(null);
  const [editedFields, setEditedFields] = useState<Set<string>>(new Set());
  const pollTimer = useRef<number | null>(null);

  const definition: AgentDefinition = value ?? EMPTY_DEFINITION;

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const autoKickedRef = useRef(false);

  const poll = useCallback(async () => {
    try {
      const res = await pollAgentDefinition(agentId, versionId);
      setStatus(res.status);
      if (res.status === 'completed' && res.data) {
        onChange(res.data);
        stopPolling();
      } else if (res.status === 'failed') {
        setError(res.error || 'Bootstrap failed. Please retry or fill the form manually.');
        stopPolling();
      } else if (res.status === 'not_started' && !autoKickedRef.current) {
        // Draft predates the Agent Definition feature OR data-dictionary save
        // didn't fire the background task. Kick it off now so the user doesn't
        // sit on an empty form forever.
        autoKickedRef.current = true;
        try {
          await bootstrapAgentDefinition(agentId, versionId);
          setStatus('pending');
        } catch (kickErr) {
          const msg = kickErr instanceof Error ? kickErr.message : 'Failed to start bootstrap';
          setError(msg);
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to poll agent definition';
      setError(msg);
    }
  }, [agentId, versionId, onChange, stopPolling]);

  useEffect(() => {
    // Initial fetch + poll if pending.
    autoKickedRef.current = false;
    void poll();
    pollTimer.current = window.setInterval(() => {
      void poll();
    }, 2000);
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, versionId]);

  const handleRetry = useCallback(async () => {
    setError(null);
    setStatus('pending');
    try {
      await bootstrapAgentDefinition(agentId, versionId);
      // Restart polling
      stopPolling();
      pollTimer.current = window.setInterval(() => {
        void poll();
      }, 2000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to start bootstrap';
      setError(msg);
      setStatus('failed');
    }
  }, [agentId, versionId, poll, stopPolling]);

  const markEdited = useCallback((field: string) => {
    setEditedFields((prev) => {
      if (prev.has(field)) return prev;
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  }, []);

  const updateField = useCallback(
    <K extends keyof AgentDefinition>(key: K, val: AgentDefinition[K]) => {
      markEdited(key as string);
      onChange({ ...definition, [key]: val });
    },
    [definition, onChange, markEdited],
  );

  const aiDrafted = useMemo(() => {
    const drafted = new Set<string>(definition.ai_drafted_fields ?? []);
    editedFields.forEach((f) => drafted.delete(f));
    return drafted;
  }, [definition.ai_drafted_fields, editedFields]);

  const BadgeForField: React.FC<{ field: string }> = ({ field }) => {
    if (aiDrafted.has(field)) {
      return (
        <span className="ml-2 inline-flex items-center rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
          ✨ AI-drafted
        </span>
      );
    }
    if (editedFields.has(field)) {
      return (
        <span className="ml-2 inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
          edited
        </span>
      );
    }
    return null;
  };

  if (status === 'pending' || status === 'not_started') {
    return <LoadingState />;
  }

  if (status === 'failed') {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
        <div className="font-medium">AI bootstrap did not complete.</div>
        <div className="mt-1">{error || 'Please retry or fill the form manually below.'}</div>
        <button
          onClick={handleRetry}
          className="mt-3 rounded-md bg-amber-100 px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-200"
        >
          Retry AI bootstrap
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-lg font-semibold text-gray-900">Agent Definition</h2>
        <p className="mt-1 text-sm text-gray-600">
          Review and edit the AI-drafted role, KPIs, rules, and sample questions. Anything you don't
          touch keeps the ✨ badge and stays as the AI suggestion.
        </p>
      </header>

      {/* Role */}
      <section>
        <label className="block text-sm font-medium text-gray-800">
          Role / Title
          <BadgeForField field="role" />
        </label>
        <input
          type="text"
          value={definition.role}
          onChange={(e) => updateField('role', e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none"
          placeholder="e.g. NCD Program Analyst"
        />
      </section>

      {/* Plain list fields */}
      {LIST_FIELDS.map(({ key, label }) => (
        <section key={key}>
          <label className="block text-sm font-medium text-gray-800">
            {label}
            <BadgeForField field={key} />
          </label>
          <textarea
            value={(definition[key] as string[]).join('\n')}
            onChange={(e) => {
              const lines = e.target.value
                .split('\n')
                .map((l) => l.trim())
                .filter((l) => l.length > 0);
              updateField(key, lines as AgentDefinition[typeof key]);
            }}
            rows={Math.max(3, (definition[key] as string[]).length + 1)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:border-purple-500 focus:outline-none"
            placeholder={`One ${label.toLowerCase()} per line`}
          />
        </section>
      ))}

      {/* Response style */}
      <section>
        <label className="block text-sm font-medium text-gray-800">
          Response Style
          <BadgeForField field="response_style" />
        </label>
        <div className="mt-1 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(['tone', 'format', 'verbosity'] as const).map((k) => (
            <div key={k}>
              <div className="text-xs text-gray-500">{k}</div>
              <input
                type="text"
                value={definition.response_style?.[k] ?? ''}
                onChange={(e) =>
                  updateField('response_style', {
                    ...definition.response_style,
                    [k]: e.target.value,
                  })
                }
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none"
                placeholder={k === 'tone' ? 'clinical-professional' : k === 'format' ? 'SQL + 1-2 sentence summary' : 'concise'}
              />
            </div>
          ))}
        </div>
      </section>

      {/* Sample questions */}
      <section>
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-800">
            Sample Questions
            <BadgeForField field="sample_questions" />
          </label>
          <button
            type="button"
            onClick={() => {
              const next: SampleQuestion[] = [
                ...definition.sample_questions,
                { question: '', sql: '', expected_summary: '', use_as_few_shot: true },
              ];
              updateField('sample_questions', next);
            }}
            className="rounded-md bg-purple-50 px-3 py-1 text-sm font-medium text-purple-700 hover:bg-purple-100"
          >
            + Add question
          </button>
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Questions marked "Use as few-shot" are indexed into this agent's example store on save —
          they ground future SQL generation.
        </p>
        <div className="mt-3 space-y-3">
          {definition.sample_questions.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              No sample questions yet.
            </div>
          )}
          {definition.sample_questions.map((q, idx) => (
            <div key={idx} className="rounded-md border border-gray-200 p-3">
              <textarea
                value={q.question}
                onChange={(e) => {
                  const next = [...definition.sample_questions];
                  next[idx] = { ...next[idx], question: e.target.value };
                  updateField('sample_questions', next);
                }}
                rows={2}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none"
                placeholder="Natural-language question (e.g. 'How many patients enrolled by month?')"
              />
              <textarea
                value={q.sql ?? ''}
                onChange={(e) => {
                  const next = [...definition.sample_questions];
                  next[idx] = { ...next[idx], sql: e.target.value };
                  updateField('sample_questions', next);
                }}
                rows={3}
                className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs focus:border-purple-500 focus:outline-none"
                placeholder="Optional: expected SQL (used as few-shot exemplar if provided)"
              />
              <div className="mt-2 flex items-center justify-between text-xs">
                <label className="flex items-center gap-2 text-gray-700">
                  <input
                    type="checkbox"
                    checked={q.use_as_few_shot ?? true}
                    onChange={(e) => {
                      const next = [...definition.sample_questions];
                      next[idx] = { ...next[idx], use_as_few_shot: e.target.checked };
                      updateField('sample_questions', next);
                    }}
                  />
                  Use as few-shot training example
                </label>
                <button
                  type="button"
                  onClick={() => {
                    const next = definition.sample_questions.filter((_, i) => i !== idx);
                    updateField('sample_questions', next);
                  }}
                  className="text-rose-600 hover:text-rose-700"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
